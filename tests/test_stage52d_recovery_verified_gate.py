"""End-to-end mocked verification of recovery gate policy (no network)."""
import json
from pathlib import Path

import pytest

from market_data.probe_cross_path_gate import (
    check_probe_state, CrossPathProbeBlocked,
)
from market_data.recovery_verified_gate import verified_recovery_override
from market_data.recovery_transport import recover_once

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_stage52d_recovery_transport import setup as recovery_setup, FakeSession, MockResponse


def test_verified_new_request_unlocks_future_fetch_not_old_request(
    recovery_setup, monkeypatch,
):
    root, opts = recovery_setup
    base = root.parent
    reports = base / "recovery_reports"
    reports.mkdir()
    new_case = reports / "stage52d_20261119_uncertain_case.json"
    new_archive = reports / "stage52d_historical_provider_credits.json"
    new_case.write_bytes(opts["case_path"].read_bytes())
    new_archive.write_bytes(opts["archive_path"].read_bytes())
    opts["case_path"] = new_case
    opts["archive_path"] = new_archive
    opts["claim_path"] = root / "recovery_txn_claim.json"
    opts["recovery_journal_path"] = root / "stage52d_new_recovery_probe.json"
    target_csv = base / "real_market" / "stage52d_new_completed.csv"
    opts["csv_path"] = target_csv

    monkeypatch.chdir(base)
    with pytest.raises(CrossPathProbeBlocked):
        check_probe_state(opts["old_probe_path"])

    old_before = opts["old_probe_path"].read_bytes()
    result = recover_once(
        approved=True, session=FakeSession(response=MockResponse()), **opts
    )
    assert result["status"] == "VERIFIED"
    assert old_before == opts["old_probe_path"].read_bytes()
    assert verified_recovery_override(opts["old_probe_path"]) is True
    assert check_probe_state(opts["old_probe_path"]) == "RECOVERY_VERIFIED_OLD_UNCERTAIN"

    journal = json.loads(opts["recovery_journal_path"].read_text())
    assert journal["status"] == "VERIFIED"
    assert json.loads(opts["old_probe_path"].read_text())["attempts"][-1]["status"] == "UNCERTAIN"

    # Changing the exact output invalidates the attestation.
    opts["csv_path"].write_text("forged")
    assert verified_recovery_override(opts["old_probe_path"]) is False
    with pytest.raises(CrossPathProbeBlocked):
        check_probe_state(opts["old_probe_path"])


def test_no_verified_override_for_empty_recovery(tmp_path):
    root = tmp_path / "api_usage"
    root.mkdir()
    old = root / "approved_research_probe.json"
    old.write_text(json.dumps({
        "version": 1,
        "attempts": [{
            "status": "UNCERTAIN",
            "started_at": "2026-11-19T13:06:33+00:00",
        }],
    }))
    assert verified_recovery_override(old) is False
    with pytest.raises(CrossPathProbeBlocked):
        check_probe_state(old)
