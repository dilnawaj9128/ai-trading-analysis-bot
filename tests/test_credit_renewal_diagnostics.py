"""Credit diagnostics are read-only and cannot authorize network calls."""
from datetime import datetime, timezone, timedelta
import json
from pathlib import Path
from unittest.mock import patch

from dashboard.credit_renewal_diagnostics import credit_renewal_readiness


def _setup(tmp_path, now, *, status="VERIFIED", age=600, left=7, reserved=1):
    root = tmp_path / "api_usage"
    root.mkdir()
    provider = root / "provider_credits.json"
    provider.write_text(json.dumps({"version": 1, "observed_at": (now - timedelta(seconds=age)).isoformat(), "credits_left": left, "credits_used": 1}))
    (root / "verified_credit_renewals.json").write_text(json.dumps({"version": 1, "attempts": [{"status": status, "request_id": "a" * 32}]}))
    return provider


def _check(path, now, *, reserved=1):
    with patch("market_data.recovery_verified_gate.verified_recovery_override", return_value=True), \
         patch("market_data.unified_request_guard._load_ledger", return_value={
             "reserved": reserved, "legacy_reserved": 0,
             "requests": {f"id_{i}": {"status": "PENDING", "credits": 1,
                        "authorized_at": (now).isoformat()}
                          for i in range(reserved)}
         }), \
         patch("market_data.provider_credit_state.load_credit_state", return_value=None):
        return credit_renewal_readiness(provider_path=path, now=now)


def test_unresolved_blocks_without_network(tmp_path):
    now = datetime(2026, 11, 20, tzinfo=timezone.utc)
    p = _setup(tmp_path, now, status="UNCERTAIN")
    assert "unresolved" in _check(p, now)["reason"]


def test_headroom_blocked(tmp_path):
    now = datetime(2026, 11, 20, tzinfo=timezone.utc)
    p = _setup(tmp_path, now)
    assert "headroom" in _check(p, now, reserved=7)["reason"]


def test_evidence_too_old(tmp_path):
    now = datetime(2026, 11, 20, tzinfo=timezone.utc)
    p = _setup(tmp_path, now, age=90000)
    assert "older" in _check(p, now)["reason"]


def test_possible_is_not_authorization(tmp_path):
    now = datetime(2026, 11, 20, tzinfo=timezone.utc)
    p = _setup(tmp_path, now)
    assert _check(p, now)["status"] == "POSSIBLE"


def test_missing_evidence_fails_closed(tmp_path):
    now = datetime(2026, 11, 20, tzinfo=timezone.utc)
    p = _setup(tmp_path, now)
    assert credit_renewal_readiness(provider_path=p, now=now)["status"] == "BLOCKED"
