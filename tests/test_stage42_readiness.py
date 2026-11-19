import json
from datetime import datetime, timedelta, timezone

import pytest

from scripts.run_stage42_readiness import (
    check_budget,
    check_provider_credits,
    readiness,
)

NOW = datetime(2026, 11, 19, 16, 0, tzinfo=timezone.utc)


def make_files(tmp_path):
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
        "minute_used": 1,
        "day": NOW.strftime("%Y-%m-%d"),
        "day_used": 10,
    }))

    credits.write_text(json.dumps({
        "version": 1,
        "observed_at": NOW.isoformat(),
        "credits_used": 10,
        "credits_left": 100,
    }))

    csv.write_text(
        "timestamp,Open,High,Low,Close\n"
        "2026-11-19T15:58:00+00:00,1.1,1.2,1.0,1.15\n"
    )

    return probe, budget, credits, csv


def test_local_budget_capacity(tmp_path):
    _, budget, _, _ = make_files(tmp_path)

    result = check_budget(budget, NOW)

    assert result["status"] == "LOCAL_CAPACITY"


def test_exhausted_minute_budget(tmp_path):
    _, budget, _, _ = make_files(tmp_path)

    data = json.loads(budget.read_text())
    data["minute_used"] = 8
    budget.write_text(json.dumps(data))

    result = check_budget(budget, NOW)

    assert result["status"] == "BLOCKED"


def test_exhausted_daily_budget(tmp_path):
    _, budget, _, _ = make_files(tmp_path)

    data = json.loads(budget.read_text())
    data["day_used"] = 800
    budget.write_text(json.dumps(data))

    result = check_budget(budget, NOW)

    assert result["status"] == "BLOCKED"


def test_corrupt_budget_blocks(tmp_path):
    _, budget, _, _ = make_files(tmp_path)
    budget.write_text("invalid-json")

    result = check_budget(budget, NOW)

    assert result["status"] == "BLOCKED"


def test_missing_budget_is_unknown(tmp_path):
    result = check_budget(
        tmp_path / "missing.json", NOW
    )

    assert result["status"] == "UNKNOWN"


def test_recent_provider_credits(tmp_path):
    _, _, credits, _ = make_files(tmp_path)

    result = check_provider_credits(credits, NOW)

    assert result["status"] == "RECENT_SNAPSHOT"


def test_stale_provider_credits(tmp_path):
    _, _, credits, _ = make_files(tmp_path)

    result = check_provider_credits(
        credits, NOW + timedelta(minutes=10)
    )

    assert result["status"] == "STALE"


def test_zero_provider_credits_blocks(tmp_path):
    _, _, credits, _ = make_files(tmp_path)

    data = json.loads(credits.read_text())
    data["credits_left"] = 0
    credits.write_text(json.dumps(data))

    result = check_provider_credits(credits, NOW)

    assert result["status"] == "BLOCKED"


def test_unresolved_probe_blocks_readiness(tmp_path):
    probe, budget, credits, csv = make_files(tmp_path)

    result = readiness(
        probe=probe,
        budget=budget,
        credits=credits,
        csv=csv,
        now=NOW,
    )

    assert result["latest_probe_status"] == "UNCERTAIN"
    assert result["collection_readiness"] == "BLOCKED"
    assert result["new_api_request_authorized"] is False
    assert result["execution_enabled"] is False


def test_missing_probe_fails_closed(tmp_path):
    probe, budget, credits, csv = make_files(tmp_path)
    probe.unlink()

    result = readiness(
        probe=probe,
        budget=budget,
        credits=credits,
        csv=csv,
        now=NOW,
    )

    assert result["latest_probe_status"] == "UNKNOWN"
    assert result["collection_readiness"] == "BLOCKED"


def test_even_verified_attempt_is_not_live_permission(
    tmp_path,
):
    probe, budget, credits, csv = make_files(tmp_path)

    data = json.loads(probe.read_text())
    data["attempts"][-1]["status"] = "VERIFIED"
    probe.write_text(json.dumps(data))

    result = readiness(
        probe=probe,
        budget=budget,
        credits=credits,
        csv=csv,
        now=NOW,
    )

    assert result["feed_mode"] == "UNKNOWN"
    assert result["collection_readiness"] == "BLOCKED"
    assert result["directional_analysis_authorized"] is False


def test_naive_now_rejected(tmp_path):
    with pytest.raises(ValueError, match="Timezone"):
        readiness(
            now=datetime(2026, 11, 19, 16, 0),
        )
