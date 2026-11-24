"""Offline regression tests: no HTTP and no API key."""
import json
from datetime import datetime, timezone

import pytest

from market_data.recovery_case import build_case
from market_data.recovery_transaction import (
    RecoveryTransactionBlocked, reserve_offline_recovery,
)


@pytest.fixture
def case(tmp_path):
    root = tmp_path / "api"
    root.mkdir()
    reports = tmp_path / "reports"
    reports.mkdir()
    evidence = {
        "approved_research_probe.json": {
            "version": 1,
            "attempts": [{"status": "UNCERTAIN",
                          "started_at": "2026-11-19T13:06:33+00:00"}],
        },
        "credit_refresh_execution.json": {"version": 1, "status": "UNCERTAIN"},
        "credit_refresh_lifecycle.json": {"version": 1, "status": "CLAIMED"},
        "provider_credits.json": {
            "version": 1, "observed_at": "2026-11-18T19:32:55+00:00",
            "credits_used": 1, "credits_left": 7,
        },
        "twelve_data_budget.json": {
            "minute": "2026-11-19T13:06Z", "minute_used": 1,
            "day": "2026-11-19", "day_used": 1,
        },
    }
    for name, value in evidence.items():
        (root / name).write_text(json.dumps(value))
    case_path = reports / "case.json"
    case_path.write_text(json.dumps(build_case(root)))
    archive = reports / "historical.json"
    archive.write_bytes((root / "provider_credits.json").read_bytes())
    old = root / "approved_research_probe.json"
    params = dict(
        provider_path=root / "provider_credits.json",
        budget_path=root / "twelve_data_budget.json",
        claim_path=root / "recovery_txn_claim.json",
        case_path=case_path,
        archive_path=archive,
        old_probe_path=old,
        explicitly_approved=True,
        now=datetime(2026, 11, 20, 6, 0, tzinfo=timezone.utc),
    )
    return root, params


def test_requires_explicit_approval(case):
    root, params = case
    params["explicitly_approved"] = False
    with pytest.raises(RecoveryTransactionBlocked):
        reserve_offline_recovery(**params)
    assert not params["claim_path"].exists()


def test_one_offline_reservation_is_durable_and_single_use(case):
    root, params = case
    old_bytes = params["old_probe_path"].read_bytes()
    provider_bytes = params["provider_path"].read_bytes()

    result = reserve_offline_recovery(**params)
    assert result["status"] == "OFFLINE_RESERVED"
    assert result["http_authorized"] is False
    assert result["local_budget_reserved"] is True
    assert params["old_probe_path"].read_bytes() == old_bytes
    assert params["provider_path"].read_bytes() == provider_bytes

    ledger = json.loads((root / "provider_credits.json.reservations.json").read_text())
    journal = json.loads((root / "provider_credits.json.authorization_journal.json").read_text())
    assert ledger["reserved"] == 1
    assert ledger["requests"][result["request_id"]]["status"] == "PENDING"
    assert journal["transactions"][result["request_id"]]["status"] == "FINALIZED"
    assert json.loads(params["claim_path"].read_text())["http_authorized"] is False
    with pytest.raises(RecoveryTransactionBlocked):
        reserve_offline_recovery(**params)
    assert ledger == json.loads((root / "provider_credits.json.reservations.json").read_text())


def test_fingerprint_tampering_rejected_before_claim(case):
    root, params = case
    params["archive_path"].write_text("{}")
    with pytest.raises(RecoveryTransactionBlocked):
        reserve_offline_recovery(**params)
    assert not params["claim_path"].exists()


def test_no_retry_after_budget_failure(case, monkeypatch):
    root, params = case
    from market_data import recovery_transaction as txn

    def fail_budget(*args, **kwargs):
        raise RuntimeError("simulated disk failure")

    monkeypatch.setattr(txn, "reserve_request", fail_budget)
    with pytest.raises(RuntimeError, match="simulated"):
        reserve_offline_recovery(**params)
    assert params["claim_path"].exists()

    with pytest.raises(RecoveryTransactionBlocked):
        reserve_offline_recovery(**params)
    journal = json.loads((root / "provider_credits.json.authorization_journal.json").read_text())
    assert any(v["status"] == "INTENT" for v in journal["transactions"].values())


def test_no_implicit_network_code(case, monkeypatch):
    root, params = case
    import requests

    def no_network(*args, **kwargs):
        raise AssertionError("Network unexpectedly called")

    monkeypatch.setattr(requests, "get", no_network)
    result = reserve_offline_recovery(**params)
    assert result["http_authorized"] is False
