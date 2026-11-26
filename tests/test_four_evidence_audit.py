"""Offline regression checks for four-task evidence audit; no external network."""
from pathlib import Path
from unittest.mock import patch

import pytest

from scripts.run_four_evidence_audit import (
    run, local_monitor, production_check, save_report,
)


def _score():
    return {
        "counts": {"WIN": 0, "LOSS": 0, "PUSH": 0, "ABSTAINED": 3},
        "invalid_evidence": [],
        "statistical_audit": {
            "nonpush_outcomes": 0, "wins": 0, "losses": 0, "pushes": 0,
            "observed_nonpush_win_rate": None,
            "status": "NO_OUTCOMES",
            "statistical_screen_passed": False,
            "break_even_nonpush_win_rate_at_payout": 1 / 1.8,
            "wilson_95pct_nonpush_win_rate": None,
            "one_sided_exact_pvalue_vs_break_even": None,
            "idealized_net_units": 0.0,
            "limitations": ["Not enough genuine directional outcomes"],
        },
    }


def test_four_evidence_audit_offline_reports_unknown_instead_of_claiming_success(tmp_path):
    with patch("scripts.run_four_evidence_audit.archive_settlement_pass",
               return_value={"captures_found": 8, "new_settlements": [],
                             "invalid_captures": []}), \
         patch("scripts.run_four_evidence_audit.prospective_scorecard",
               return_value=_score()), \
         patch("scripts.run_four_evidence_audit.health_once",
               side_effect=AssertionError("No HTTP permitted")):
        report = run(journal=tmp_path / "observations")
    assert report["prediction_accuracy"]["nonpush"] == 0
    assert report["prediction_accuracy"]["status"] == "INSUFFICIENT_OUTCOMES"
    assert report["profitability_statistics"]["statistical_edge_proven"] is False
    assert report["long_session_monitoring"]["status"] == "NOT_RUN"
    assert report["production_deployment"]["remote_production_deployment_verified"] is False
    assert report["data_provider_http_requests"] == 0
    assert report["broker_orders"] == 0
    path = save_report(report, tmp_path)
    assert path.is_file()


def test_local_monitor_rejects_external_host():
    with pytest.raises(ValueError):
        local_monitor(health_url="http://example.com/api/health",
                      duration_seconds=60)


def test_local_monitor_rejects_short_virtual_test():
    with pytest.raises(ValueError):
        local_monitor(health_url="http://127.0.0.1:8000/api/health",
                      duration_seconds=2)


def test_production_requires_https_and_nonlocal():
    with pytest.raises(ValueError):
        production_check(health_url="http://example.com/api/health")
    with pytest.raises(ValueError):
        production_check(health_url="https://127.0.0.1/api/health")
    assert production_check(health_url="https://example.com/api/health",
                            probe=lambda url: False)["remote_production_deployment_verified"] is False


def test_health_session_failure_is_not_misrepresented():
    ticker = iter([0., 0., 0.])
    result = local_monitor(
        health_url="http://127.0.0.1:8000/api/health",
        duration_seconds=60, interval_seconds=30,
        clock=lambda: next(ticker),
        probe=lambda url: False,
    )
    assert result["status"] == "HEALTH_SESSION_INCOMPLETE_OR_FAILED"
    assert result["actual_uptime_verified"] is False
    assert result["samples"] == 1
