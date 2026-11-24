"""All mock transport; never require Twelve Data API credentials."""
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import pytest
import requests

from market_data.provider_credit_state import load_credit_state
from market_data.verified_credit_renewal import (
    VerifiedCreditRenewalBlocked, renew_verified_credits_once,
)
from scripts.run_one_normal_fetch import fetch_one_research_snapshot


class Response:
    status_code = 200
    headers = {"api-credits-used": "2", "api-credits-left": "6"}
    def json(self):
        now = datetime.now(timezone.utc).replace(second=0, microsecond=0) - timedelta(minutes=2)
        return {"meta": {"symbol": "EUR/USD", "interval": "1min"},
                "values": [
                    {"datetime": (now - timedelta(minutes=i)).strftime("%Y-%m-%d %H:%M:%S"),
                     "open": "1.101", "high": "1.103", "low": "1.100", "close": "1.102"}
                    for i in range(120)
                ]}
    def raise_for_status(self):
        return None


class Session:
    def __init__(self, error=None, response=None):
        self.calls = 0
        self.error = error
        self.response = response or Response()
    def get(self, *args, **kwargs):
        self.calls += 1
        if self.error:
            raise self.error
        return self.response


@pytest.fixture
def prepared(tmp_path, monkeypatch):
    root = tmp_path / "api"
    root.mkdir()
    now = datetime.now(timezone.utc)
    provider = root / "provider_credits.json"
    budget = root / "twelve_data_budget.json"
    old = root / "approved_research_probe.json"
    old.write_text(json.dumps({"version": 1, "attempts": [{"status": "UNCERTAIN"}]}))
    provider.write_text(json.dumps({
        "version": 1, "observed_at": (now - timedelta(minutes=7)).isoformat(),
        "credits_used": 1, "credits_left": 7,
    }))
    budget.write_text(json.dumps({
        "minute": now.strftime("%Y-%m-%dT%H:%MZ"), "minute_used": 0,
        "day": now.strftime("%Y-%m-%d"), "day_used": 1,
    }))
    # Attestation implementation is tested separately by the real Stage52D
    # suite; isolate the renewal transaction and transport here.
    monkeypatch.setattr("market_data.verified_credit_renewal.verified_recovery_override", lambda path: True)
    return {"provider_path": provider, "budget_path": budget, "old_probe_path": old,
            "now": now, "api_key": "mock-key"}


def test_no_approval_never_calls_http(prepared):
    session = Session()
    with pytest.raises(VerifiedCreditRenewalBlocked):
        renew_verified_credits_once(approved=False, session=session, **prepared)
    assert session.calls == 0
    assert not (prepared["provider_path"].parent / "verified_credit_renewals.json").exists()


def test_no_verified_recovery_never_calls_http(prepared, monkeypatch):
    monkeypatch.setattr("market_data.verified_credit_renewal.verified_recovery_override", lambda path: False)
    session = Session()
    with pytest.raises(VerifiedCreditRenewalBlocked):
        renew_verified_credits_once(approved=True, session=session, **prepared)
    assert session.calls == 0


def test_one_renewal_updates_snapshot_and_preserves_old(prepared):
    session = Session()
    old = prepared["old_probe_path"].read_bytes()
    result = renew_verified_credits_once(approved=True, session=session, **prepared)
    assert result["status"] == "VERIFIED"
    assert result["candles"] == 120
    assert session.calls == 1
    assert prepared["old_probe_path"].read_bytes() == old
    assert load_credit_state(path=prepared["provider_path"]) is not None
    ledger = json.loads((prepared["provider_path"].parent / "provider_credits.json.reservations.json").read_text())
    assert ledger["reserved"] == 1
    budget = json.loads(prepared["budget_path"].read_text())
    assert budget["minute_used"] == 1
    log = json.loads((prepared["provider_path"].parent / "verified_credit_renewals.json").read_text())
    assert log["attempts"][-1]["status"] == "VERIFIED"
    # A second attempt cannot silently consume another credit while fresh.
    with pytest.raises(VerifiedCreditRenewalBlocked):
        renew_verified_credits_once(approved=True, session=session, **prepared)
    assert session.calls == 1


def test_timeout_durable_uncertain_and_never_retries(prepared):
    session = Session(error=requests.exceptions.ReadTimeout("simulated"))
    with pytest.raises(requests.exceptions.ReadTimeout):
        renew_verified_credits_once(approved=True, session=session, **prepared)
    assert session.calls == 1
    log = json.loads((prepared["provider_path"].parent / "verified_credit_renewals.json").read_text())
    assert log["attempts"][-1]["status"] == "UNCERTAIN"
    with pytest.raises(VerifiedCreditRenewalBlocked):
        renew_verified_credits_once(approved=True, session=session, **prepared)
    assert session.calls == 1
    ledger = json.loads((prepared["provider_path"].parent / "provider_credits.json.reservations.json").read_text())
    assert ledger["reserved"] == 1
    assert list(ledger["requests"].values())[0]["status"] == "UNCERTAIN"


def test_missing_headers_leaves_uncertain(prepared):
    session = Session()
    session.response.headers = {}
    with pytest.raises(VerifiedCreditRenewalBlocked):
        renew_verified_credits_once(approved=True, session=session, **prepared)
    assert session.calls == 1
    log = json.loads((prepared["provider_path"].parent / "verified_credit_renewals.json").read_text())
    assert log["attempts"][-1]["status"] == "UNCERTAIN"


def test_very_old_snapshot_blocks_before_http(prepared):
    evidence = json.loads(prepared["provider_path"].read_text())
    evidence["observed_at"] = (prepared["now"] - timedelta(days=2)).isoformat()
    prepared["provider_path"].write_text(json.dumps(evidence))
    session = Session()
    with pytest.raises(VerifiedCreditRenewalBlocked):
        renew_verified_credits_once(approved=True, session=session, **prepared)
    assert session.calls == 0


def test_insufficient_credit_headroom_blocks_before_http(prepared):
    evidence = json.loads(prepared["provider_path"].read_text())
    evidence["credits_left"] = 1
    prepared["provider_path"].write_text(json.dumps(evidence))
    session = Session()
    with pytest.raises(VerifiedCreditRenewalBlocked):
        renew_verified_credits_once(approved=True, session=session, **prepared)
    assert session.calls == 0


def test_combined_fetch_requires_approval_and_key():
    with pytest.raises(ValueError):
        fetch_one_research_snapshot(approved=False, api_key="fake")
    with pytest.raises(ValueError):
        fetch_one_research_snapshot(approved=True, api_key=None)


def test_combined_fetch_renews_only_if_stale():
    with patch("scripts.run_one_normal_fetch.load_credit_state", return_value=None), \
         patch("scripts.run_one_normal_fetch.renew_verified_credits_once", return_value={"status": "VERIFIED"}) as renew, \
         patch("scripts.run_one_normal_fetch.fetch_authorized_live_candles", return_value={"candles": 120}) as fetch:
        outcome = fetch_one_research_snapshot(approved=True, api_key="fake")
    assert outcome["credits_renewed"] is True
    assert outcome["candles"] == 120
    renew.assert_called_once()
    fetch.assert_called_once()


def test_combined_fetch_no_renewal_when_fresh():
    with patch("scripts.run_one_normal_fetch.load_credit_state", return_value=object()), \
         patch("scripts.run_one_normal_fetch.renew_verified_credits_once") as renew, \
         patch("scripts.run_one_normal_fetch.fetch_authorized_live_candles", return_value={"candles": 120}):
        outcome = fetch_one_research_snapshot(approved=True, api_key="fake")
    assert outcome["credits_renewed"] is False
    renew.assert_not_called()
