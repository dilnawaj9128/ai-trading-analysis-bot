"""Stage 50: completed-candle entry timing regression tests."""

from datetime import timedelta

import pandas as pd
import pytest


def calculate_outcome(signal, entry, exit_price):
    if signal not in ("UP", "DOWN"):
        raise ValueError("Invalid direction")

    if entry == exit_price:
        return "PUSH"

    if signal == "UP":
        return "WIN" if exit_price > entry else "LOSS"

    return "WIN" if exit_price < entry else "LOSS"


def test_next_open_entry_and_15m_expiry_alignment():
    # Candle timestamps represent candle OPEN times.
    times = pd.date_range(
        "2026-11-12T10:00:00Z",
        periods=20,
        freq="min",
    )

    signal_index = 0
    entry_index = signal_index + 1
    expiry_index = signal_index + 15

    signal_available = times[signal_index] + timedelta(minutes=1)
    entry_time = times[entry_index]
    expiry_time = times[expiry_index] + timedelta(minutes=1)

    assert entry_time >= signal_available
    assert expiry_time - entry_time == timedelta(minutes=15)


@pytest.mark.parametrize(
    "signal,entry,exit_price,expected",
    [
        ("UP", 1.1000, 1.1002, "WIN"),
        ("UP", 1.1002, 1.1000, "LOSS"),
        ("DOWN", 1.1002, 1.1000, "WIN"),
        ("DOWN", 1.1000, 1.1002, "LOSS"),
        ("UP", 1.1000, 1.1000, "PUSH"),
        ("DOWN", 1.1000, 1.1000, "PUSH"),
    ],
)
def test_outcome_calculation(signal, entry, exit_price, expected):
    assert calculate_outcome(signal, entry, exit_price) == expected


def test_invalid_direction_rejected():
    with pytest.raises(ValueError):
        calculate_outcome("NO TRADE", 1.1, 1.2)


def test_real_dataset_timestamp_alignment():
    from research.stage29_backtest import load_candles

    df = load_candles(
        "data/historical/eurusd_1min_1day.csv"
    )

    assert len(df) == 1440

    step = pd.Timedelta(minutes=1)
    assert df.timestamp.diff().iloc[1:].eq(step).all()

    for i in range(59, len(df) - 15):
        signal_available = df.timestamp.iloc[i] + step
        entry_time = df.timestamp.iloc[i + 1]
        expiry_time = df.timestamp.iloc[i + 15] + step

        assert entry_time >= signal_available
        assert expiry_time - entry_time == pd.Timedelta(minutes=15)
