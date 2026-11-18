import pandas as pd
import pytest

from analysis.historical_signal_comparison import (
    compare_directions,
    evaluate_historical_signal,
)


def sample_candles():
    timestamps = pd.date_range(
        "2026-11-12 10:00",
        periods=100,
        freq="min",
        tz="UTC",
    )

    return pd.DataFrame({
        "timestamp": timestamps,
        "Open": [1.10] * 100,
        "High": [1.20] * 100,
        "Low": [1.00] * 100,
        "Close": [1.10] * 100,
    })


def test_unknown_feed_blocks_directional_signal():
    result = evaluate_historical_signal(
        sample_candles(),
        selected_index=60,
    )

    assert result["signal"] == "NO TRADE"
    assert result["comparison"] == "NOT_EVALUATED"


def test_only_past_candles_used():
    result = evaluate_historical_signal(
        sample_candles(),
        selected_index=60,
    )

    assert result["candles_used_for_signal"] == 61


def test_future_outcome_does_not_change_signal():
    first = sample_candles()
    second = sample_candles()

    second.loc[75, "Close"] = 1.15

    a = evaluate_historical_signal(first, selected_index=60)
    b = evaluate_historical_signal(second, selected_index=60)

    assert a["signal"] == b["signal"]
    assert a["historical_outcome"] != b["historical_outcome"]


def test_comparison_rules():
    assert compare_directions("UP", "UP") == "MATCH"
    assert compare_directions("DOWN", "UP") == "MISMATCH"
    assert compare_directions("UP", "FLAT") == "FLAT_OUTCOME"
    assert compare_directions("NO TRADE", "DOWN") == "NOT_EVALUATED"


def test_invalid_direction_rejected():
    with pytest.raises(ValueError):
        compare_directions("BUY", "UP")


def test_missing_future_candle_blocks():
    frame = sample_candles()
    frame.loc[65, "timestamp"] += pd.Timedelta(minutes=3)

    with pytest.raises(ValueError):
        evaluate_historical_signal(frame, selected_index=60)
