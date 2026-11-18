import numpy as np
import pandas as pd
import pytest

from analysis.ml_trainer import FEATURES
from analysis.walk_forward import evaluate_walk_forward


def sample_dataset(n=200):
    timestamps = pd.date_range(
        "2026-11-12 10:00",
        periods=n,
        freq="min",
        tz="UTC",
    )

    labels = np.arange(n) % 2

    data = pd.DataFrame({
        "timestamp": timestamps,
        "outcome_timestamp": timestamps + pd.Timedelta(minutes=15),
        "label_up_15m": labels,
    })

    for i, feature in enumerate(FEATURES):
        data[feature] = (
            np.sin(np.arange(n) * (i + 1) * 0.07)
            + np.arange(n) * 0.0001
        )

    return data


def test_walk_forward_produces_four_model_results():
    result = evaluate_walk_forward(
        sample_dataset(),
        min_train=100,
        test_size=30,
        max_folds=1,
    )

    assert len(result["folds"]) == 4
    assert result["folds"]["fold"].nunique() == 1
    assert result["analysis_only"] is True
    assert result["execution_enabled"] is False


def test_duplicate_timestamps_rejected():
    data = sample_dataset()
    data.loc[1, "timestamp"] = data.loc[0, "timestamp"]

    with pytest.raises(ValueError):
        evaluate_walk_forward(
            data, min_train=100, test_size=30
        )


def test_wrong_outcome_horizon_rejected():
    data = sample_dataset()
    data.loc[50, "outcome_timestamp"] = (
        data.loc[50, "timestamp"] + pd.Timedelta(minutes=10)
    )

    with pytest.raises(ValueError):
        evaluate_walk_forward(
            data, min_train=100, test_size=30
        )


def test_invalid_feature_rejected():
    data = sample_dataset()
    data.loc[10, FEATURES[0]] = float("inf")

    with pytest.raises(ValueError):
        evaluate_walk_forward(
            data, min_train=100, test_size=30
        )
