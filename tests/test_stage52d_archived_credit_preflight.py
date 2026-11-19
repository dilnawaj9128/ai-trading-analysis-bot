"""Stage 52D: archived historical credits and fresh current credits."""

import json
from datetime import datetime, timedelta, timezone

from market_data.recovery_case import build_case
from market_data.recovery_preflight import evaluate_preflight

NOW = datetime(2026, 11, 20, 12, 0, tzinfo=timezone.utc)


def setup(tmp_path):
    root = tmp_path / "api"
    root.mkdir()

    data = {
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
                NOW - timedelta(days=2)
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

    for name, payload in data.items():
        (root / name).write_text(json.dumps(payload))

    case = tmp_path / "case.json"
    case.write_text(json.dumps(build_case(root)))

    current = root / "provider_credits.json"
    archive = tmp_path / "historical_provider.json"
    archive.write_bytes(current.read_bytes())

    return root, case, archive, current


def check(root, case, archive):
    return evaluate_preflight(
        root=root,
        case_path=case,
        archive_path=archive,
        now=NOW,
    )


def test_archived_snapshot_with_stale_current_blocks(tmp_path):
    root, case, archive, _ = setup(tmp_path)

    result = check(root, case, archive)

    assert result["evidence_matches"] is True
    assert result["fresh_provider_credits"] is False
    assert result["preflight"] == "BLOCKED"


def test_fresh_current_snapshot_does_not_verify_old_probe(tmp_path):
    root, case, archive, current = setup(tmp_path)

    data = json.loads(current.read_text())
    data["observed_at"] = NOW.isoformat()
    current.write_text(json.dumps(data))

    result = check(root, case, archive)

    assert result["evidence_matches"] is True
    assert result["original_still_uncertain"] is True
    assert result["preflight"] == "READY_FOR_APPROVAL_REVIEW"
    assert result["new_api_request_authorized"] is False
    assert result["retry_allowed"] is False


def test_tampered_archive_blocks(tmp_path):
    root, case, archive, _ = setup(tmp_path)

    archive.write_text('{"version": 1, "credits_left": 999}')

    result = check(root, case, archive)

    assert result["preflight"] == "BLOCKED"
    assert result["evidence_matches"] is False


def test_archive_and_current_remain_unchanged(tmp_path):
    root, case, archive, current = setup(tmp_path)

    before_archive = archive.read_bytes()
    before_current = current.read_bytes()
    before_case = case.read_bytes()

    check(root, case, archive)

    assert archive.read_bytes() == before_archive
    assert current.read_bytes() == before_current
    assert case.read_bytes() == before_case
