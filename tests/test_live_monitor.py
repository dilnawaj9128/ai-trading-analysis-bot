
import json
from datetime import datetime, timedelta, timezone

import pytest

from config.market_config import create_research_config
from market_data.live_monitor import (
    record_poll_result,
    read_monitor_state,
    reserve_poll,
    run_monitor_poll,
)
from market_data.twelve_data_client import (
    BudgetExceeded,
    MarketDataError,
)


NOW = datetime(
    2026, 11, 13, 6, 0,
    tzinfo=timezone.utc,
)


def config():
    return create_research_config(
        "quotex", "forex", "EUR/USD", "1min", 15
    )


def test_first_poll_allowed(tmp_path):
    result = reserve_poll(
        interval_minutes=3,
        path=tmp_path / "scheduler.json",
        now=NOW,
    )
    assert result["allowed"] is True


def test_immediate_duplicate_blocked(tmp_path):
    path = tmp_path / "scheduler.json"

    reserve_poll(path=path, now=NOW)
    result = reserve_poll(path=path, now=NOW)

    assert result["allowed"] is False


def test_three_minute_interval(tmp_path):
    path = tmp_path / "scheduler.json"

    reserve_poll(path=path, now=NOW)

    early = reserve_poll(
        path=path,
        now=NOW + timedelta(minutes=2),
    )
    assert early["allowed"] is False

    later = reserve_poll(
        path=path,
        now=NOW + timedelta(minutes=3),
    )
    assert later["allowed"] is True


def test_reject_invalid_intervals(tmp_path):
    for invalid in (0, 2, 10, True, "3"):
        with pytest.raises(ValueError):
            reserve_poll(
                interval_minutes=invalid,
                path=tmp_path / "scheduler.json",
                now=NOW,
            )


def test_error_backoff(tmp_path):
    path = tmp_path / "scheduler.json"

    reserve_poll(
        interval_minutes=1,
        path=path,
        now=NOW,
    )

    record_poll_result(
        status="ERROR",
        path=path,
        now=NOW,
    )

    early = reserve_poll(
        interval_minutes=1,
        path=path,
        now=NOW + timedelta(minutes=2),
    )
    assert early["allowed"] is False

    later = reserve_poll(
        interval_minutes=1,
        path=path,
        now=NOW + timedelta(minutes=3),
    )
    assert later["allowed"] is True


def test_corrupt_scheduler_fails_closed(tmp_path):
    path = tmp_path / "scheduler.json"
    path.write_text("{broken", encoding="utf-8")

    with pytest.raises(MarketDataError):
        reserve_poll(path=path, now=NOW)


def test_successful_mock_poll(tmp_path):
    calls = []

    def fake_fetch(cfg):
        calls.append(cfg.symbol)
        return {
            "symbol": cfg.symbol,
            "analysis_only": True,
            "execution_enabled": False,
        }

    path = tmp_path / "scheduler.json"

    first = run_monitor_poll(
        config(),
        interval_minutes=3,
        scheduler_path=path,
        fetcher=fake_fetch,
        now=NOW,
    )

    assert first["status"] == "SUCCESS"
    assert calls == ["EUR/USD"]

    second = run_monitor_poll(
        config(),
        interval_minutes=3,
        scheduler_path=path,
        fetcher=fake_fetch,
        now=NOW,
    )

    assert second["status"] == "WAITING"
    assert len(calls) == 1


def test_budget_blocked_without_retry(tmp_path):
    calls = []

    def fake_fetch(cfg):
        calls.append(cfg.symbol)
        raise BudgetExceeded("Budget exhausted")

    path = tmp_path / "scheduler.json"

    result = run_monitor_poll(
        config(),
        interval_minutes=1,
        scheduler_path=path,
        fetcher=fake_fetch,
        now=NOW,
    )

    assert result["status"] == "BUDGET_BLOCKED"
    assert len(calls) == 1

    state = read_monitor_state(path)
    assert state["last_status"] == "BUDGET_BLOCKED"


def test_api_error_backoff(tmp_path):
    def fake_fetch(cfg):
        raise MarketDataError("Provider unavailable")

    path = tmp_path / "scheduler.json"

    result = run_monitor_poll(
        config(),
        interval_minutes=1,
        scheduler_path=path,
        fetcher=fake_fetch,
        now=NOW,
    )

    assert result["status"] == "ERROR"

    later = reserve_poll(
        interval_minutes=1,
        path=path,
        now=NOW + timedelta(minutes=2),
    )

    assert later["allowed"] is False


def test_scheduler_state_persists(tmp_path):
    path = tmp_path / "scheduler.json"

    reserve_poll(path=path, now=NOW)

    state = json.loads(
        path.read_text(encoding="utf-8")
    )

    assert state["last_status"] == "RESERVED"
    assert "next_allowed_utc" in state

