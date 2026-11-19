"""Stage 52D Part 4D recovery route diagnosis tests."""

import json
from datetime import datetime, timedelta, timezone

from market_data.recovery_case import build_case
from market_data.recovery_deadlock import diagnose


NOW = datetime(2026, 11, 20, 12, 0, tzinfo=timezone.utc)


def setup_evidence(tmp_path, *, fresh=False):
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

    for name, data in payloads.items():
        (root / name).write_text(json.dumps(data))

    case_path = tmp_path / "case.json"
    case_path.write_text(json.dumps(build_case(root)))

    archive_path = tmp_path / "historical.json"
    provider = root / "provider_credits.json"
    archive_path.write_bytes(provider.read_bytes())

    if fresh:
        current = json.loads(provider.read_text())
        current["observed_at"] = NOW.isoformat()
        provider.write_text(json.dumps(current))

    return root, case_path, archive_path


def run(paths):
    root, case, archive = paths
    return diagnose(
        root=root,
        case_path=case,
        archive_path=archive,
        now=NOW,
    )


def test_detects_existing_authorization_deadlock(tmp_path):
    result = run(setup_evidence(tmp_path))

    assert "EXISTING_PROBE_GATE_BLOCKS_HTTP" in result["reasons"]
    assert "PREVIOUS_REFRESH_CANNOT_BE_REUSED" in result["reasons"]
    assert "FRESH_PROVIDER_CREDITS_UNAVAILABLE" in result["reasons"]


def test_fresh_snapshot_does_not_unlock_old_probe(tmp_path):
    result = run(setup_evidence(tmp_path, fresh=True))

    assert result["fresh_provider_credits"] is True
    assert result["original_probe_status"] == "UNCERTAIN"
    assert result["normal_fetch_allowed"] is False


def test_recovery_request_not_authorized(tmp_path):
    result = run(setup_evidence(tmp_path))

    assert result["recovery_http_implemented"] is False
    assert result["recovery_http_authorized"] is False
    assert result["old_request_retry_allowed"] is False
    assert result["trading_enabled"] is False


def test_diagnostic_preserves_all_evidence(tmp_path):
    paths = setup_evidence(tmp_path)
    root, case, archive = paths

    files = list(root.glob("*.json")) + [case, archive]
    before = {str(p): p.read_bytes() for p in files}

    run(paths)

    for path in files:
        assert path.read_bytes() == before[str(path)]
