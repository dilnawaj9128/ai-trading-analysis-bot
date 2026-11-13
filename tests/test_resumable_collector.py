import pandas as pd
import pytest

from market_data.resumable_collector import (
    validate_batch,
    atomic_csv_save,
)
from market_data.twelve_data_client import MarketDataError


def sample_frame():
    return pd.DataFrame({
        "timestamp": pd.date_range(
            "2026-11-12 10:00",
            periods=3,
            freq="min",
            tz="UTC",
        ),
        "Open": [1.10, 1.11, 1.12],
        "High": [1.12, 1.13, 1.14],
        "Low": [1.09, 1.10, 1.11],
        "Close": [1.11, 1.12, 1.13],
    })


def validate(frame):
    return validate_batch(
        frame,
        pd.Timestamp("2026-11-12 10:00", tz="UTC"),
        pd.Timestamp("2026-11-12 10:03", tz="UTC"),
        "1min",
    )


def test_valid_batch():
    assert len(validate(sample_frame())) == 3


def test_duplicate_rejected():
    frame = sample_frame()
    frame.loc[1, "timestamp"] = frame.loc[0, "timestamp"]
    with pytest.raises(MarketDataError):
        validate(frame)


def test_outside_window_rejected():
    frame = sample_frame()
    frame.loc[2, "timestamp"] = pd.Timestamp(
        "2026-11-12 10:03", tz="UTC"
    )
    with pytest.raises(MarketDataError):
        validate(frame)


def test_invalid_ohlc_rejected():
    frame = sample_frame()
    frame.loc[0, "High"] = 1.0
    with pytest.raises(MarketDataError):
        validate(frame)


def test_atomic_csv_save(tmp_path):
    path = tmp_path / "batch.csv"
    atomic_csv_save(sample_frame(), path)

    assert path.exists()
    assert len(pd.read_csv(path)) == 3
    assert not list(tmp_path.glob(".partial_*"))
