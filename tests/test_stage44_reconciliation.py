import json
from datetime import datetime, timezone

import pytest

from scripts.run_stage44_reconciliation import (
    compare_usage,
    reconcile,
    validate_snapshot,
)
from scripts.run_stage41_evidence_audit import (
    write_evidence_report,
)

REQUEST_TIME = datetime(
    2026, 11, 19, 13, 6, 33, tzinfo=timezone.utc
)


def make_evidence(before=10, after=11):
    return {
        "version": 1,
        "before": {
            "source": "provider_dashboard_manual",
            "observed_at": "2026-11-19T13:00:00+00:00",
            "usage_day": "2026-11-19",
            "daily_credits_used": before,
        },
        "after": {
            "source": "provider_dashboard_manual",
            "observed_at": "2026-11-19T13:10:00+00:00",
            "usage_day": "2026-11-19",
            "daily_credits_used": after,
        },
    }


def make_files(tmp_path):
    probe = tmp_path / "probe.json"
    evidence = tmp_path / "usage.json"

    probe.write_text(json.dumps({
        "version": 1,
        "attempts": [{
            "status": "UNCERTAIN",
            "started_at": REQUEST_TIME.isoformat(),
        }],
    }))

    evidence.write_text(json.dumps(make_evidence()))
    return probe, evidence


def test_usage_increase_not_attributed():
    result = compare_usage(make_evidence(10, 11), REQUEST_TIME)
    assert result["observed_delta"] == 1
    assert result["finding"] == "USAGE_INCREASE_NOT_ATTRIBUTABLE"
    assert result["request_success_proven"] is False


def test_equal_usage_does_not_prove_failure():
    result = compare_usage(make_evidence(10, 10), REQUEST_TIME)
    assert result["finding"] == "NO_OBSERVABLE_USAGE_CHANGE"
    assert result["request_failure_proven"] is False


def test_decreasing_counter_inconclusive():
    result = compare_usage(make_evidence(11, 10), REQUEST_TIME)
    assert result["finding"] == "COUNTER_DECREASE_INCONCLUSIVE"


def test_invalid_negative_credit_rejected():
    with pytest.raises(ValueError):
        compare_usage(make_evidence(-1, 4), REQUEST_TIME)


def test_string_credit_rejected():
    evidence = make_evidence()
    evidence["before"]["daily_credits_used"] = "10"
    with pytest.raises(ValueError):
        compare_usage(evidence, REQUEST_TIME)


def test_wrong_evidence_source_rejected():
    evidence = make_evidence()
    evidence["before"]["source"] = "unknown"
    with pytest.raises(ValueError):
        compare_usage(evidence, REQUEST_TIME)


def test_no_timezone_rejected():
    evidence = make_evidence()
    evidence["before"]["observed_at"] = "2026-11-19T13:00:00"
    with pytest.raises(ValueError, match="Timezone"):
        compare_usage(evidence, REQUEST_TIME)


def test_unbracketed_request_rejected():
    evidence = make_evidence()
    evidence["after"]["observed_at"] = (
        "2026-11-19T13:05:00+00:00"
    )
    with pytest.raises(ValueError, match="bracket"):
        compare_usage(evidence, REQUEST_TIME)


def test_stale_snapshot_rejected():
    evidence = make_evidence()
    evidence["before"]["observed_at"] = (
        "2026-11-19T05:00:00+00:00"
    )
    with pytest.raises(ValueError, match="too far"):
        compare_usage(evidence, REQUEST_TIME)


def test_missing_evidence_stays_inconclusive(tmp_path):
    probe, evidence = make_files(tmp_path)
    evidence.unlink()

    result = reconcile(probe=probe, evidence=evidence)

    assert result["comparison"]["finding"] == "INCONCLUSIVE"
    assert result["new_api_request_authorized"] is False


def test_reconciliation_does_not_modify_files(tmp_path):
    probe, evidence = make_files(tmp_path)
    original_probe = probe.read_bytes()
    original_evidence = evidence.read_bytes()

    result = reconcile(probe=probe, evidence=evidence)

    assert result["reconciliation_status"] == (
        "MANUAL_REVIEW_REQUIRED"
    )
    assert result["provider_request_resolved"] is False
    assert result["api_requests_executed"] == 0
    assert probe.read_bytes() == original_probe
    assert evidence.read_bytes() == original_evidence


def test_export_reconciliation_is_immutable(tmp_path):
    probe, evidence = make_files(tmp_path)
    result = reconcile(probe=probe, evidence=evidence)

    out = tmp_path / "reports"
    first, created = write_evidence_report(result, out)
    second, duplicate = write_evidence_report(result, out)

    assert created is True
    assert duplicate is False
    assert first == second
    assert json.loads(first.read_text())["stage"] == 44
