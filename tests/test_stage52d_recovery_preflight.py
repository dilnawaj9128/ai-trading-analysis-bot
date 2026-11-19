import json
from datetime import datetime, timedelta, timezone

import pytest

from market_data.recovery_case import build_case
from market_data.recovery_preflight import (
    RecoveryPreflightError,
    evaluate_preflight,
)


NOW = datetime(2026, 11, 20, 12, 0, tzinfo=timezone.utc)


def setup_case(tmp_path, *, credits_age=60):
    root = tmp_path / "api"
    root.mkdir()

    payloads = {
        "approved_research_probe.json": {
            "version": 1,
            "attempts": [{
                "status": "UNCERTAIN",
                "started_at": "2026-11-19T13:06:33+00:00",
            }],
        },
        "credit_refresh_execution.json": {
            "status": "UNCERTAIN",
        },
        "credit_refresh_lifecycle.json": {
            "status": "CLAIMED",
        },
        "provider_credits.json": {
            "version": 1,
            "observed_at": (
                NOW - timedelta(seconds=credits_age)
            ).isoformat(),
            "credits_used": 1,
            "credits_left": 7,
        },
        "twelve_data_budget.json": {
            "minute": NOW.strftime("%Y-%m-%dT%H:%MZ"),
            "minute_used": 0,
            "day": NOW.strftime("%Y-%m-%d"),
            "day_used": 0,
        },
    }

    for filename, payload in payloads.items():
        (root / filename).write_text(json.dumps(payload))

    case_path = tmp_path / "case.json"
    case_path.write_text(json.dumps(build_case(root)))

    return root, case_path


def check(root, case_path):
    return evaluate_preflight(
        root=root,
        case_path=case_path,
        now=NOW,
    )


def test_eligible_conditions_still_require_approval(tmp_path):
    root, case = setup_case(tmp_path)

    result = check(root, case)

    assert result["preflight"] == "READY_FOR_APPROVAL_REVIEW"
    assert result["new_api_request_authorized"] is False
    assert result["retry_allowed"] is False


def test_stale_provider_snapshot_blocks(tmp_path):
    root, case = setup_case(tmp_path, credits_age=600)

    result = check(root, case)

    assert result["preflight"] == "BLOCKED"
    assert "FRESH_PROVIDER_CREDITS_REQUIRED" in result["reasons"]


def test_changed_original_journal_blocks(tmp_path):
    root, case = setup_case(tmp_path)
    path = root / "approved_research_probe.json"

    data = json.loads(path.read_text())
    data["attempts"][-1]["status"] = "VERIFIED"
    path.write_text(json.dumps(data))

    result = check(root, case)

    assert result["preflight"] == "BLOCKED"
    assert not result["evidence_matches"]


def test_exhausted_budget_blocks(tmp_path):
    root, case = setup_case(tmp_path)
    path = root / "twelve_data_budget.json"

    data = json.loads(path.read_text())
    data["minute_used"] = 8
    path.write_text(json.dumps(data))

    result = check(root, case)

    assert result["preflight"] == "BLOCKED"
    assert not result["local_budget_ok"]


def test_read_only_and_no_retry(tmp_path):
    root, case = setup_case(tmp_path)

    before = {
        p: p.read_bytes()
        for p in list(root.glob("*.json")) + [case]
    }

    result = check(root, case)

    assert result["retry_allowed"] is False
    assert result["new_api_request_authorized"] is False

    for path, content in before.items():
        assert path.read_bytes() == content


def test_invalid_case_fails_closed(tmp_path):
    root, case = setup_case(tmp_path)
    case.write_text("{invalid")

    with pytest.raises(RecoveryPreflightError):
        check(root, case)
