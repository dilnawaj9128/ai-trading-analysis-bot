"""Offline-only tests for receipt-bound independent quota recovery."""
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import pytest
import requests

from market_data.independent_usage_recovery import (
    IndependentRecoveryBlocked, recover_once, verified_independent_recovery,
)
from scripts.recover_credit_blockers_once import run


class FakeResponse:
    status_code = 200
    def __init__(self):
        self.headers = {"api-credits-used": "1", "api-credits-left": "7"}
    def json(self):
        now = datetime.now(timezone.utc)
        return {
            "timestamp": now.strftime("%Y-%m-%d %H:%M:%S"),
            "current_usage": 1, "plan_limit": 8,
            "daily_usage": 2, "plan_daily_limit": 800,
            "plan_category": "basic",
        }
    def raise_for_status(self):
        pass


class FakeSession:
    def __init__(self, error=None):
        self.error = error
        self.calls = 0
    def get(self, url, **kwargs):
        self.calls += 1
        assert url == "https://api.twelvedata.com/api_usage"
        assert kwargs["allow_redirects"] is False
        assert kwargs["timeout"] == (5, 30)
        if self.error:
            raise self.error
        return FakeResponse()


@pytest.fixture
def files(tmp_path, monkeypatch):
    root = tmp_path / "api"
    root.mkdir()
    provider = root / "provider_credits.json"
    provider.write_text(json.dumps({
        "version": 1,
        "observed_at": (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat(),
        "credits_used": 2, "credits_left": 6,
    }))
    (root / "approved_research_probe.json").write_text('{"version":1,"attempts":[]}')
    monkeypatch.setattr(
        "market_data.independent_usage_recovery.verified_recovery_override",
        lambda _: True,
    )
    return provider, root / "twelve_data_budget.json"


def test_no_approval_never_sends_request(files):
    provider, budget = files
    session = FakeSession()
    with pytest.raises(IndependentRecoveryBlocked):
        recover_once(approved=False, api_key="test", provider_path=provider,
                     budget_path=budget, session=session)
    assert session.calls == 0


def test_valid_new_usage_settles_only_own_request(files):
    provider, budget = files
    session = FakeSession()
    result = recover_once(
        approved=True, api_key="test", provider_path=provider,
        budget_path=budget, session=session,
    )
    assert session.calls == 1
    assert result["status"] == "VERIFIED_NEW_USAGE_ONLY"
    assert result["old_requests_settled"] == 0
    ledger = json.loads(
        provider.with_name("provider_credits.json.reservations.json").read_text()
    )
    assert ledger["reserved"] == 0
    assert len(ledger["requests"]) == 1
    assert next(iter(ledger["requests"].values()))["status"] == "SETTLED"
    assert verified_independent_recovery(provider_path=provider)


def test_failed_request_remains_uncertain_and_does_not_retry(files):
    provider, budget = files
    session = FakeSession(error=requests.exceptions.ConnectionError("offline mock"))
    with pytest.raises(requests.exceptions.ConnectionError):
        recover_once(approved=True, api_key="test", provider_path=provider,
                     budget_path=budget, session=session)
    assert session.calls == 1
    ledger = json.loads(
        provider.with_name("provider_credits.json.reservations.json").read_text()
    )
    assert ledger["reserved"] == 1
    assert next(iter(ledger["requests"].values()))["status"] == "UNCERTAIN"
    assert not verified_independent_recovery(provider_path=provider)
    with pytest.raises(IndependentRecoveryBlocked):
        recover_once(approved=True, api_key="test", provider_path=provider,
                     budget_path=budget, session=session)
    assert session.calls == 1


def test_cli_reports_old_19_unresolved_and_new_verified_current_usage(tmp_path):
    pre = {"status": "BLOCKED", "independent_current_usage_verified": False,
           "reasons": ["CREDIT_RENEWAL_UNRESOLVED"]}
    post = {"status": "PRECHECK_ONLY_EXISTING_REQUEST_GUARD_STILL_REQUIRED",
            "independent_current_usage_verified": True, "reasons": []}
    with patch("scripts.recover_credit_blockers_once.reconcile_verified_historical",
               return_value={"status": "RECONCILED"}), \
         patch("scripts.recover_credit_blockers_once.eligibility",
               side_effect=[pre, post]), \
         patch("scripts.recover_credit_blockers_once.reservation_audit",
               side_effect=[{"outstanding_reserved": 19},
                            {"outstanding_reserved": 19}]), \
         patch("scripts.recover_credit_blockers_once.recover_once",
               return_value={"status": "VERIFIED_NEW_USAGE_ONLY", "new_http_requests": 1}):
        output = run(approved=True, api_key="fixture", provider=tmp_path / "credits.json")
    assert output["status"] == "FRESH_OPERATIONAL_USAGE_VERIFIED_HISTORICAL_UNRESOLVED"
    assert output["before"]["reservations"] == 19
    assert output["after"]["reservations"] == 19
    assert output["old_pending_or_uncertain_not_manually_cleared"]
