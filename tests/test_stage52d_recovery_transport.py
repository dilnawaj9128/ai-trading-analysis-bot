"""Mocked recovery HTTP tests; no Twelve Data key or network access."""
import json
from datetime import datetime, timezone, timedelta

import pytest
import requests

from market_data.recovery_case import build_case
from market_data.recovery_transport import recover_once, RecoveryTransportBlocked


@pytest.fixture
def setup(tmp_path):
    root = tmp_path / "api"
    reports = tmp_path / "reports"
    root.mkdir()
    reports.mkdir()
    old = root / "approved_research_probe.json"
    evidence = {
        "approved_research_probe.json": {
            "version": 1, "attempts": [{
                "status": "UNCERTAIN",
                "started_at": "2026-11-19T13:06:33+00:00",
            }],
        },
        "credit_refresh_execution.json": {"version": 1, "status": "UNCERTAIN"},
        "credit_refresh_lifecycle.json": {"version": 1, "status": "CLAIMED"},
        "provider_credits.json": {
            "version": 1,
            "observed_at": "2026-11-18T19:32:55+00:00",
            "credits_used": 1,
            "credits_left": 7,
        },
        "twelve_data_budget.json": {
            "minute": "2026-11-19T13:06Z",
            "minute_used": 1,
            "day": "2026-11-19",
            "day_used": 1,
        },
    }
    for name, data in evidence.items():
        (root / name).write_text(json.dumps(data))
    case_path = reports / "case.json"
    case_path.write_text(json.dumps(build_case(root)))
    archive_path = reports / "provider_archive.json"
    archive_path.write_bytes((root / "provider_credits.json").read_bytes())
    args = dict(
        old_probe_path=old,
        case_path=case_path,
        archive_path=archive_path,
        provider_path=root / "provider_credits.json",
        budget_path=root / "twelve_data_budget.json",
        claim_path=root / "recovery_txn_claim.json",
        recovery_journal_path=root / "new_recovery.json",
        csv_path=tmp_path / "candles.csv",
        now=datetime(2026, 11, 20, 6, 0, tzinfo=timezone.utc),
        api_key="MOCK_ONLY",
    )
    return root, args


class MockResponse:
    status_code = 200
    headers = {"api-credits-used": "2", "api-credits-left": "6"}

    def __init__(self):
        # Build completed candles relative to the test execution clock;
        # no look-ahead, valid OHLC, and stable UTC minute boundaries.
        latest = datetime.now(timezone.utc).replace(second=0, microsecond=0) - timedelta(minutes=2)
        self.payload = {
            "meta": {"symbol": "EUR/USD", "interval": "1min"},
            "values": [
                {
                    "datetime": (latest - timedelta(minutes=i)).strftime("%Y-%m-%d %H:%M:%S"),
                    "open": "1.101", "high": "1.103", "low": "1.100", "close": "1.102",
                } for i in range(120)
            ],
        }

    def json(self):
        return self.payload

    def raise_for_status(self):
        return None


class FakeSession:
    def __init__(self, response=None, failure=None):
        self.calls = 0
        self.response = response
        self.failure = failure

    def get(self, url, **kwargs):
        self.calls += 1
        if self.failure:
            raise self.failure
        return self.response


def test_mocked_single_http_and_budget_exactly_once(setup):
    root, args = setup
    old_bytes = args["old_probe_path"].read_bytes()
    session = FakeSession(response=MockResponse())

    result = recover_once(approved=True, session=session, **args)
    assert result["status"] == "VERIFIED"
    assert result["http_requests"] == 1
    assert session.calls == 1
    assert args["old_probe_path"].read_bytes() == old_bytes
    assert args["csv_path"].exists()

    state = json.loads(args["budget_path"].read_text())
    assert state["minute_used"] == 1
    assert state["day_used"] == 1

    journal = json.loads(args["recovery_journal_path"].read_text())
    assert journal["status"] == "VERIFIED"
    ledger = json.loads((root / "provider_credits.json.reservations.json").read_text())
    assert ledger["reserved"] == 1
    with pytest.raises(Exception):
        recover_once(approved=True, session=session, **args)
    assert session.calls == 1


def test_no_approval_no_budget_and_no_http(setup):
    root, args = setup
    session = FakeSession(response=MockResponse())
    with pytest.raises(RecoveryTransportBlocked):
        recover_once(approved=False, session=session, **args)
    assert session.calls == 0
    assert not args["claim_path"].exists()


def test_read_timeout_fails_closed_and_prevents_retry(setup):
    root, args = setup
    session = FakeSession(failure=requests.exceptions.ReadTimeout("offline"))
    old_bytes = args["old_probe_path"].read_bytes()
    with pytest.raises(requests.exceptions.ReadTimeout):
        recover_once(approved=True, session=session, **args)
    assert session.calls == 1
    assert args["old_probe_path"].read_bytes() == old_bytes
    journal = json.loads(args["recovery_journal_path"].read_text())
    assert journal["status"] == "UNCERTAIN"
    ledger = json.loads((root / "provider_credits.json.reservations.json").read_text())
    assert ledger["reserved"] == 1
    with pytest.raises(Exception):
        recover_once(approved=True, session=session, **args)
    assert session.calls == 1


def test_changed_archive_blocks_before_http(setup):
    root, args = setup
    args["archive_path"].write_text("{}")
    session = FakeSession(response=MockResponse())
    with pytest.raises(Exception):
        recover_once(approved=True, session=session, **args)
    assert session.calls == 0
    assert not args["claim_path"].exists()


def test_missing_credit_headers_does_not_verify(setup):
    root, args = setup
    class NoHeaders(MockResponse):
        headers = {}
    session = FakeSession(response=NoHeaders())
    with pytest.raises(RecoveryTransportBlocked):
        recover_once(approved=True, session=session, **args)
    journal = json.loads(args["recovery_journal_path"].read_text())
    assert journal["status"] == "UNCERTAIN"
    assert session.calls == 1
