import pandas as pd
import pytest

from market_data.resumable_collector import validate_batch
from market_data.twelve_data_client import MarketDataError


START = pd.Timestamp("2026-11-12 10:00", tz="UTC")
END = pd.Timestamp("2026-11-12 10:05", tz="UTC")


def candles(minutes):
    return pd.DataFrame({
        "timestamp": [
            START + pd.Timedelta(minutes=i)
            for i in minutes
        ],
        "Open": 1.10,
        "High": 1.12,
        "Low": 1.09,
        "Close": 1.11,
    })


def test_complete_batch_accepted():
    frame = candles([0, 1, 2, 3, 4])

    result = validate_batch(
        frame, START, END, "1min",
        require_complete=True,
    )

    assert len(result) == 5


def test_missing_middle_candle_rejected():
    frame = candles([0, 1, 3, 4])

    with pytest.raises(MarketDataError, match="Incomplete batch"):
        validate_batch(
            frame, START, END, "1min",
            require_complete=True,
        )


def test_missing_first_candle_rejected():
    frame = candles([1, 2, 3, 4])

    with pytest.raises(MarketDataError, match="Incomplete batch"):
        validate_batch(
            frame, START, END, "1min",
            require_complete=True,
        )


def test_non_strict_mode_remains_compatible():
    frame = candles([0, 1, 3, 4])

    result = validate_batch(
        frame, START, END, "1min",
    )

    assert len(result) == 4
