from datetime import datetime, timezone, timedelta

import pytest

from market_data.providers.candle_repository import CandleRepository
from market_data.providers.research_adapter import (
    load_candle_frame,
    analyze_stored_candles,
)


def populate(repo, count=70, skip=None):
    start = datetime(
        2026, 11, 22, 10, 0,
        tzinfo=timezone.utc
    )

    for i in range(count):
        if i == skip:
            continue

        price = 1.10 + i * 0.00001

        repo.save_candle({
            "timestamp": start + timedelta(minutes=i),
            "open": price,
            "high": price + 0.0002,
            "low": price - 0.0002,
            "close": price + 0.00005,
        })


def test_load_frame(tmp_path):
    path = tmp_path / "market.db"
    repo = CandleRepository(path)
    populate(repo)

    frame = load_candle_frame(path)

    assert len(frame) == 70
    assert list(frame.columns) == [
        "timestamp", "Open", "High", "Low", "Close"
    ]


def test_insufficient_history(tmp_path):
    path = tmp_path / "market.db"
    repo = CandleRepository(path)
    populate(repo, count=30)

    with pytest.raises(ValueError):
        load_candle_frame(path)


def test_missing_candle_rejected(tmp_path):
    path = tmp_path / "market.db"
    repo = CandleRepository(path)
    populate(repo, skip=35)

    with pytest.raises(ValueError):
        load_candle_frame(path)


def test_research_analysis_no_trade(tmp_path):
    path = tmp_path / "market.db"
    repo = CandleRepository(path)
    populate(repo)

    result = analyze_stored_candles(path)

    assert result["signal"] == "NO TRADE"
    assert result["analysis_only"] is True
    assert result["execution_enabled"] is False
    assert result["feed_verified"] is False
