import pandas as pd
import pytest

from analysis.historical_batch_report import (
    build_historical_report,
)


def sample_candles():
    timestamps = pd.date_range(
        "2026-11-12 10:00",
        periods=120,
        freq="min",
        tz="UTC",
    )

    return pd.DataFrame({
        "timestamp": timestamps,
        "Open": [1.10] * 120,
        "High": [1.20] * 120,
        "Low": [1.00] * 120,
        "Close": [1.10] * 120,
    })


def test_batch_observation_count():
    report = build_historical_report(sample_candles())
    assert report["summary"]["total_observations"] == 4


def test_all_flat_observations():
    report = build_historical_report(sample_candles())
    assert report["summary"]["flat"] == 4
    assert report["summary"]["up"] == 0


def test_historical_up_outcome():
    frame = sample_candles()
    frame.loc[74, "Close"] = 1.15

    report = build_historical_report(frame)

    assert report["summary"]["up"] == 1
    assert report["summary"]["total_observations"] == 4


def test_invalid_window_fails_closed():
    frame = sample_candles()
    frame.loc[65, "timestamp"] += pd.Timedelta(minutes=3)

    with pytest.raises(ValueError):
        build_historical_report(frame)
