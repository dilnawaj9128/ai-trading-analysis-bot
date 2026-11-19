import json
from datetime import datetime, timezone

import pytest

from scripts.run_stage43_recovery_plan import (
    build_plan,
    recovery_plan,
)
from scripts.run_stage41_evidence_audit import (
    write_evidence_report,
)

NOW = datetime(2026, 11, 19, 16, 0, tzinfo=timezone.utc)


def sample_report(
    latest="UNCERTAIN",
    budget="LOCAL_CAPACITY",
    credits="STALE",
):
    return {
        "stage": 42,
        "latest_probe_status": latest,
        "budget": {"status": budget},
        "provider_credits": {"status": credits},
        "checked_at_utc": NOW.isoformat(),
    }


def setup_files(tmp_path):
    probe = tmp_path / "probe.json"
    budget = tmp_path / "budget.json"
    credits = tmp_path / "credits.json"
    csv = tmp_path / "candles.csv"

    probe.write_text(json.dumps({
        "version": 1,
        "attempts": [{
            "status": "UNCERTAIN",
            "started_at": NOW.isoformat(),
        }],
    }))

    budget.write_text(json.dumps({
        "minute": NOW.strftime("%Y-%m-%dT%H:%MZ"),
        "minute_used": 0,
        "day": NOW.strftime("%Y-%m-%d"),
        "day_used": 1,
    }))

    credits.write_text(json.dumps({
        "version": 1,
        "observed_at": NOW.isoformat(),
        "credits_left": 100,
    }))

    csv.write_text(
        "timestamp,Open,High,Low,Close\n"
        "2026-11-19T15:58:00+00:00,1.1,1.2,1.0,1.15\n"
    )

    return probe, budget, credits, csv


def test_uncertain_request_blocks_acquisition():
    result = build_plan(sample_report())

    assert result["acquisition"]["status"] == "BLOCKED"
    assert (
        "REVIEW_UNRESOLVED_ATTEMPT"
        in result["acquisition"]["blockers"]
    )


def test_stale_credits_block_acquisition():
    result = build_plan(sample_report())

    assert (
        "VERIFY_PROVIDER_CREDITS"
        in result["acquisition"]["blockers"]
    )


def test_available_local_budget_not_authorization():
    result = build_plan(sample_report())

    assert result["acquisition"]["api_request_approved"] is False


def test_exhausted_local_budget_blocks():
    result = build_plan(
        sample_report(budget="BLOCKED")
    )

    assert (
        "CHECK_LOCAL_BUDGET"
        in result["acquisition"]["blockers"]
    )


def test_even_clean_status_requires_manual_approval():
    result = build_plan(
        sample_report(
            latest="VERIFIED",
            budget="LOCAL_CAPACITY",
            credits="RECENT_SNAPSHOT",
        )
    )

    assert result["acquisition"]["status"] == (
        "MANUAL_APPROVAL_STILL_REQUIRED"
    )
    assert result["acquisition"]["api_request_approved"] is False


def test_broker_parity_not_acquisition_blocker():
    result = build_plan(sample_report())

    assert (
        "CHECK_BROKER_PARITY"
        not in result["acquisition"]["blockers"]
    )
    assert (
        "CHECK_BROKER_PARITY"
        in result["signal_validation"]["blockers"]
    )


def test_signal_validation_always_blocked():
    result = build_plan(
        sample_report(
            latest="VERIFIED",
            credits="RECENT_SNAPSHOT",
        )
    )

    assert result["signal_validation"]["status"] == "BLOCKED"
    assert (
        result["signal_validation"]["directional_signals_approved"]
        is False
    )


def test_bad_readiness_report_fails():
    with pytest.raises(ValueError):
        build_plan({"stage": 41})


def test_read_only_integration(tmp_path):
    probe, budget, credits, csv = setup_files(tmp_path)

    before = {
        "probe": probe.read_bytes(),
        "budget": budget.read_bytes(),
        "credits": credits.read_bytes(),
        "csv": csv.read_bytes(),
    }

    result = recovery_plan(
        probe=probe,
        budget=budget,
        credits=credits,
        csv=csv,
        now=NOW,
    )

    assert result["acquisition"]["status"] == "BLOCKED"
    assert result["api_requests_executed"] == 0
    assert result["execution_enabled"] is False

    assert probe.read_bytes() == before["probe"]
    assert budget.read_bytes() == before["budget"]
    assert credits.read_bytes() == before["credits"]
    assert csv.read_bytes() == before["csv"]


def test_export_does_not_overwrite(tmp_path):
    report = build_plan(sample_report())
    directory = tmp_path / "reports"

    first, created = write_evidence_report(
        report, directory
    )
    second, created_again = write_evidence_report(
        report, directory
    )

    assert created is True
    assert created_again is False
    assert first == second
    assert json.loads(first.read_text())["stage"] == 43
