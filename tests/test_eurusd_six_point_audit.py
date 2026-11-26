"""Deterministic offline six-task audit tests, no network or orders."""
from datetime import datetime, timedelta, timezone

import pytest

from scripts.run_eurusd_six_point_audit import (
    simulated_monitor_policy, feed_evidence,
    forward_evidence, deployment_evidence, run_audit, write_report,
)

def test_virtual_24_hour_policy_never_claims_real_uptime():
    result = simulated_monitor_policy()
    assert result["status"].startswith("VIRTUAL_24H_POLICY_TEST_PASSED")
    assert result["simulated_attempts"] == 3
    assert result["actual_24h_provider_uptime_verified"] is False
    assert result["auto_stopped_on_failure"] is True

def test_missing_provider_capture_is_not_verified(tmp_path):
    result = feed_evidence(provider_captures=tmp_path)
    assert result["status"] == "PROVIDER_CLASS_VERIFIED_CAPTURE_MISSING"
    assert result["account_specific_live_mode_verified"] is False

def test_empty_forward_campaign_cannot_claim_accuracy(tmp_path):
    a, b, c = forward_evidence(journal=tmp_path)
    assert a["status"] == "NO_DIRECTIONAL_OUTCOMES"
    assert a["observed_win_rate"] is None
    assert b["observed_nonpush"] == 0
    assert b["remaining_nonpush"] == 100
    assert c["profitable_live_performance_proven"] is False

def test_deployment_missing_root_not_success(tmp_path):
    result = deployment_evidence(root=tmp_path)
    assert result["status"] == "LOCAL_INSTALLATION_INCOMPLETE"
    assert result["remote_public_deployment_verified"] is False

def test_invalid_payout_cannot_pass(tmp_path):
    with pytest.raises(ValueError):
        forward_evidence(journal=tmp_path, payout=0)
    with pytest.raises(ValueError):
        forward_evidence(journal=tmp_path, payout=1.01)

def test_audit_writes_new_report_without_overwrite(tmp_path):
    report = run_audit(
        journal=tmp_path / "journal",
        provider_captures=tmp_path / "capture",
        historical=tmp_path / "history.csv",
        root=tmp_path,
        now=datetime(2026, 11, 24, 15, 0, tzinfo=timezone.utc),
    )
    assert report["claims"]["provider_requests"] == 0
    assert report["claims"]["live_signal"] == "NO TRADE"
    assert report["tasks"]["2_unseen_prediction_accuracy"]["prediction_accuracy_proven"] is False
    assert report["tasks"]["4_statistical_edge"]["profitable_live_performance_proven"] is False
    path = write_report(report, tmp_path / "reports")
    assert path.is_file()
    path_again = write_report(report, tmp_path / "reports")
    assert path_again.is_file()
    assert path != path_again
