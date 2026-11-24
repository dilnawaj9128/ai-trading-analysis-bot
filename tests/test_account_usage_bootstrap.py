"""Offline-only tests for explicit account usage credit bootstrap."""
import json
from datetime import datetime, timedelta, timezone

import pytest
import requests

from market_data.account_usage_bootstrap import (
    AccountUsageBootstrapBlocked, _usage, bootstrap_account_usage_once,
)
from market_data.provider_credit_state import load_credit_state


class FakeResponse:
    status_code = 200

    def __init__(self, now):
        self.headers = {"api-credits-used": "1", "api-credits-left": "7"}
        self.payload = {
            "timestamp": now.strftime("%Y-%m-%d %H:%M:%S"),
            "current_usage": 1, "plan_limit": 8,
            "daily_usage": 2, "plan_daily_limit": 800,
            "plan_category": "basic",
        }

    def json(self):
        return self.payload

    def raise_for_status(self):
        pass


class FakeSession:
    def __init__(self, response=None, error=None):
        self.response, self.error, self.calls = response, error, 0

    def get(self, *args, **kwargs):
        self.calls += 1
        assert args[0] == "https://api.twelvedata.com/api_usage"
        assert kwargs["allow_redirects"] is False
        assert kwargs["headers"]["Authorization"].startswith("apikey ")
        if self.error:
            raise self.error
        return self.response


@pytest.fixture
def prepared(tmp_path, monkeypatch):
    now = datetime.now(timezone.utc)
    root = tmp_path / "api"
    root.mkdir()
    provider = root / "provider_credits.json"
    provider.write_text(json.dumps({
        "version": 1,
        "observed_at": (now - timedelta(days=3)).isoformat(),
        "credits_used": 2, "credits_left": 6,
    }))
    old = root / "approved_research_probe.json"
    old.write_text('{"version":1,"attempts":[{"status":"UNCERTAIN"}]}')
    monkeypatch.setattr(
        "market_data.account_usage_bootstrap.verified_recovery_override",
        lambda _: True,
    )
    return {
        "provider_path": provider,
        "old_probe_path": old,
        "budget_path": root / "budget.json",
        "journal_path": root / "account_usage_bootstrap.json",
        "api_key": "OFFLINE_TEST_KEY",
        "now": now,
    }


def test_no_approval_means_no_request(prepared):
    session = FakeSession()
    with pytest.raises(AccountUsageBootstrapBlocked, match="Explicit"):
        bootstrap_account_usage_once(approved=False, session=session, **prepared)
    assert session.calls == 0


def test_valid_usage_response():
    now = datetime.now(timezone.utc)
    response = FakeResponse(now)
    snapshot = _usage(response.json(), response.headers, response_time=now)
    assert snapshot.credits_left == 7


def test_usage_timestamp_or_header_disagreement_fails_closed():
    now = datetime.now(timezone.utc)
    response = FakeResponse(now)
    response.payload["timestamp"] = (now - timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S")
    with pytest.raises(AccountUsageBootstrapBlocked):
        _usage(response.json(), response.headers, response_time=now)
    response = FakeResponse(now)
    response.headers["api-credits-left"] = "100"
    with pytest.raises(AccountUsageBootstrapBlocked):
        _usage(response.json(), response.headers, response_time=now)


def test_one_bootstrap_updates_only_current_credit_evidence(prepared):
    session = FakeSession(response=FakeResponse(datetime.now(timezone.utc)))
    before = prepared["old_probe_path"].read_bytes()
    result = bootstrap_account_usage_once(approved=True, session=session, **prepared)
    assert result["status"] == "VERIFIED"
    assert result["http_requests"] == 1
    assert session.calls == 1
    assert load_credit_state(path=prepared["provider_path"]) is not None
    assert prepared["old_probe_path"].read_bytes() == before
    log = json.loads(prepared["journal_path"].read_text())
    assert log["attempts"][-1]["status"] == "VERIFIED"
    ledger = json.loads(
        prepared["provider_path"].with_name("provider_credits.json.reservations.json").read_text()
    )
    assert ledger["reserved"] == 1
    with pytest.raises(AccountUsageBootstrapBlocked, match="already fresh"):
        bootstrap_account_usage_once(approved=True, session=session, **prepared)
    assert session.calls == 1


def test_timeout_blocks_retry_and_preserves_journal(prepared):
    session = FakeSession(error=requests.exceptions.ReadTimeout("offline"))
    with pytest.raises(requests.exceptions.ReadTimeout):
        bootstrap_account_usage_once(approved=True, session=session, **prepared)
    record = json.loads(prepared["journal_path"].read_text())
    assert record["attempts"][-1]["status"] == "UNCERTAIN"
    assert session.calls == 1
    with pytest.raises(AccountUsageBootstrapBlocked, match="unresolved"):
        bootstrap_account_usage_once(approved=True, session=session, **prepared)
    assert session.calls == 1
