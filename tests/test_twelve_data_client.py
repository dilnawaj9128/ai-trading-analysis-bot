
from datetime import datetime, timezone, timedelta

import pytest

from config.market_config import (
    ResearchConfig,
    create_research_config,
)
from market_data import twelve_data_client as td


NOW = datetime(
    2026, 11, 12, 12, 0, 0, tzinfo=timezone.utc
)


def config():
    return create_research_config(
        "quotex", "forex", "EUR/USD", "1min", 15
    )


def payload():
    return {
        "status": "ok",
        "meta": {
            "symbol": "EUR/USD",
            "interval": "1min",
        },
        "values": [
            {
                "datetime": "2026-11-12 11:58:00",
                "open": "1.1000",
                "high": "1.1010",
                "low": "1.0990",
                "close": "1.1005",
            },
            {
                "datetime": "2026-11-12 11:59:00",
                "open": "1.1005",
                "high": "1.1015",
                "low": "1.1000",
                "close": "1.1010",
            },
        ],
    }


def test_valid_candles():
    result = td.parse_candles(payload(), config(), NOW)
    assert result["candles"] == 2
    assert result["gaps"] == 0
    assert result["stale"] is False
    assert result["execution_enabled"] is False


def test_duplicate_timestamp_rejected():
    data = payload()
    data["values"].append(data["values"][0].copy())
    with pytest.raises(td.MarketDataError):
        td.parse_candles(data, config(), NOW)


def test_invalid_ohlc_rejected():
    data = payload()
    data["values"][0]["high"] = "1.0000"
    with pytest.raises(td.MarketDataError):
        td.parse_candles(data, config(), NOW)


def test_symbol_mismatch_rejected():
    data = payload()
    data["meta"]["symbol"] = "GBP/USD"
    with pytest.raises(td.MarketDataError):
        td.parse_candles(data, config(), NOW)


def test_interval_mismatch_rejected():
    data = payload()
    data["meta"]["interval"] = "5min"
    with pytest.raises(td.MarketDataError):
        td.parse_candles(data, config(), NOW)


def test_provider_error_rejected():
    with pytest.raises(td.MarketDataError):
        td.parse_candles(
            {"status": "error", "message": "Invalid key"},
            config(),
            NOW,
        )


def test_future_timestamp_rejected():
    data = payload()
    data["values"][0]["datetime"] = (
        "2026-11-12 12:01:00"
    )
    with pytest.raises(td.MarketDataError):
        td.parse_candles(data, config(), NOW)


def test_incomplete_candle_excluded():
    data = payload()
    data["values"].append({
        "datetime": "2026-11-12 12:00:00",
        "open": "1.1000",
        "high": "1.1010",
        "low": "1.0990",
        "close": "1.1005",
    })
    result = td.parse_candles(data, config(), NOW)
    assert result["candles"] == 2


def test_stale_detection():
    later = NOW + timedelta(minutes=10)
    result = td.parse_candles(payload(), config(), later)
    assert result["stale"] is True


def test_gap_detection():
    data = payload()
    data["values"][0]["datetime"] = (
        "2026-11-12 11:55:00"
    )
    result = td.parse_candles(data, config(), NOW)
    assert result["gaps"] == 1


def test_budget_persists_and_blocks(tmp_path, monkeypatch):
    monkeypatch.setattr(td, "MINUTE_LIMIT", 2)
    monkeypatch.setattr(td, "DAY_LIMIT", 3)

    path = tmp_path / "budget.json"

    td.reserve_request(path, NOW)
    state = td.reserve_request(path, NOW)

    assert state["minute_used"] == 2

    with pytest.raises(td.BudgetExceeded):
        td.reserve_request(path, NOW)

    next_minute = NOW + timedelta(minutes=1)
    state = td.reserve_request(path, next_minute)
    assert state["day_used"] == 3

    with pytest.raises(td.BudgetExceeded):
        td.reserve_request(
            path, next_minute + timedelta(minutes=1)
        )


def test_corrupted_budget_fails_closed(tmp_path):
    path = tmp_path / "budget.json"
    path.write_text("{broken", encoding="utf-8")

    with pytest.raises(td.MarketDataError):
        td.reserve_request(path, NOW)


def test_missing_key_does_not_consume_budget(tmp_path):
    path = tmp_path / "budget.json"

    with pytest.raises(td.MarketDataError):
        td.fetch_recent_candles(
            config(), api_key="", state_path=path,
        )

    assert not path.exists()


def test_modified_config_rejected(tmp_path):
    path = tmp_path / "budget.json"

    unsafe = ResearchConfig(
        platform="quotex",
        market="forex",
        symbol="EUR/USD",
        timeframe="1min",
        expiry_minutes=15,
        execution_enabled=True,
    )

    with pytest.raises(td.MarketDataError):
        td.fetch_recent_candles(
            unsafe,
            api_key="fake-test-key",
            state_path=path,
        )

    assert not path.exists()


def test_mocked_request(tmp_path):
    """Legacy caller must delegate to authorized transport."""
    from unittest.mock import patch

    expected = {
        "candles": 2,
        "analysis_only": True,
        "execution_enabled": False,
    }

    class NoNetwork:
        def get(self, *args, **kwargs):
            raise AssertionError("Legacy HTTP must not execute")

    session = NoNetwork()
    budget = tmp_path / "budget.json"

    with patch(
        "market_data.authorized_live_fetch.fetch_authorized_live_candles",
        return_value=expected,
    ) as authorized:
        result = td.fetch_recent_candles(
            config(),
            api_key="fake-test-key",
            state_path=budget,
            now=NOW,
            session=session,
        )

    assert result == expected
    authorized.assert_called_once_with(
        config(),
        api_key="fake-test-key",
        state_path=budget,
        now=NOW,
        session=session,
    )
    assert not budget.exists()
