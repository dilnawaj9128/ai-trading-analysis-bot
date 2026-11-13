import pandas as pd
import pytest

from analysis.training_dataset import (
    build_training_dataset,
    save_training_dataset,
)


def sample(n=120):
    timestamps = pd.date_range(
        "2026-01-05T00:00:00Z",
        periods=n,
        freq="min",
    )

    close = [100 + i * 0.01 for i in range(n)]

    return pd.DataFrame({
        "timestamp": timestamps,
        "Open": close,
        "High": [x + 0.1 for x in close],
        "Low": [x - 0.1 for x in close],
        "Close": close,
    })


def test_labels_are_15_minutes_ahead():
    result = build_training_dataset(sample())

    assert not result.empty

    difference = (
        result["outcome_timestamp"]
        - result["timestamp"]
    )

    assert (
        difference == pd.Timedelta(minutes=15)
    ).all()

    assert (result["label_up_15m"] == 1).all()


def test_gap_excludes_crossing_windows():
    frame = sample()

    frame.loc[75:, "timestamp"] += pd.Timedelta(
        minutes=1
    )

    result = build_training_dataset(frame)

    gap = pd.Timestamp("2026-01-05T01:15:00Z")

    assert not (
        (result["timestamp"] < gap)
        & (result["outcome_timestamp"] > gap)
    ).any()


def test_duplicate_timestamp_rejected():
    frame = sample()

    frame.loc[10, "timestamp"] = frame.loc[
        9, "timestamp"
    ]

    with pytest.raises(ValueError):
        build_training_dataset(frame)


def test_short_data_rejected():
    with pytest.raises(ValueError):
        build_training_dataset(sample(74))


def test_no_overwrite(tmp_path):
    result = build_training_dataset(sample())

    path = tmp_path / "training.csv"

    save_training_dataset(result, path)

    with pytest.raises(FileExistsError):
        save_training_dataset(result, path)
