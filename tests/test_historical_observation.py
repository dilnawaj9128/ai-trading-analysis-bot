import pandas as pd
import pytest

from analysis.historical_observation import (
    HistoricalObservationError,
    evaluate_historical_window,
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


def test_upward_historical_movement():
    frame = sample_candles()
    frame.loc[75, "Close"] = 1.15

    result = evaluate_historical_window(
        frame, selected_index=60
    )

    assert result["historical_direction"] == "UP"
    assert result["expiry_minutes"] == 15


def test_downward_historical_movement():
    frame = sample_candles()
    frame.loc[75, "Close"] = 1.05

    result = evaluate_historical_window(
        frame, selected_index=60
    )

    assert result["historical_direction"] == "DOWN"


def test_flat_historical_movement():
    result = evaluate_historical_window(
        sample_candles(), selected_index=60
    )

    assert result["historical_direction"] == "FLAT"


def test_no_future_candles_in_indicator_input():
    frame = sample_candles()
    result = evaluate_historical_window(
        frame, selected_index=60
    )

    assert len(result["indicator_input"]) == 61
    assert result["indicator_input"]["timestamp"].max() == frame.loc[
        60, "timestamp"
    ]


def test_missing_candle_blocks_evaluation():
    frame = sample_candles()
    frame.loc[65, "timestamp"] += pd.Timedelta(minutes=3)

    with pytest.raises(HistoricalObservationError):
        evaluate_historical_window(
            frame, selected_index=60
        )


def test_incomplete_window_blocks():
    with pytest.raises(HistoricalObservationError):
        evaluate_historical_window(
            sample_candles(), selected_index=90
        )


def test_invalid_expiry_blocks():
    with pytest.raises(HistoricalObservationError):
        evaluate_historical_window(
            sample_candles(),
            selected_index=60,
            expiry_minutes=5,
        )
