"""Tests for offline walk-forward research."""

import pandas as pd
import pytest

from scripts.run_stage36_walk_forward import (
    score_window,
    walk_forward,
)


def sample(n=850):
    times = pd.date_range(
        "2026-11-01 00:00",
        periods=n,
        freq="min",
        tz="UTC",
    )
    close = [1.10 + i * 0.00001 for i in range(n)]

    return pd.DataFrame({
        "timestamp": times,
        "Open": close,
        "High": [x + 0.0001 for x in close],
        "Low": [x - 0.0001 for x in close],
        "Close": close,
    })


class FakeCache:
    """Deterministic signal source, no market prediction."""

    def __init__(self, candles):
        self.candles = candles

    def for_variant(self, variant):
        def predict(prefix):
            assert len(prefix) <= len(self.candles)
            assert prefix.iloc[-1]["timestamp"] == (
                self.candles.iloc[len(prefix) - 1]["timestamp"]
            )
            return "UP"

        return predict


def test_future_bars_not_passed_to_signal():
    df = sample(150)
    seen = []

    def signal(prefix):
        seen.append(len(prefix))
        return "UP"

    result = score_window(df, signal, 59, 120)

    assert seen
    assert max(seen) <= 105

    for trade in result["trades"]:
        assert trade["expiry_index"] < 120


def test_train_outcomes_end_before_test_starts():
    df = sample()

    report = walk_forward(
        df,
        initial_train=620,
        test_size=100,
        cache_factory=FakeCache,
    )

    assert report["folds"]

    for fold in report["folds"]:
        assert fold["selected"] is not None

        for trade in fold["test"]["trades"]:
            assert trade["signal_index"] >= fold["test_start"]
            assert trade["expiry_index"] < fold["test_end"]


def test_walk_forward_nonoverlapping_test_trades():
    report = walk_forward(
        sample(),
        initial_train=620,
        test_size=100,
        cache_factory=FakeCache,
    )

    trades = report["test_trades"]

    for previous, current in zip(trades, trades[1:]):
        assert current["signal_index"] >= previous["expiry_index"]


def test_insufficient_training_abstains():
    report = walk_forward(
        sample(180),
        initial_train=100,
        test_size=60,
        cache_factory=FakeCache,
    )

    assert all(fold["selected"] is None for fold in report["folds"])
    assert report["aggregate"]["resolved"] == 0


def test_contiguous_gap_skipped():
    df = sample(150)
    df.loc[90:, "timestamp"] += pd.Timedelta(minutes=2)

    result = score_window(
        df, lambda prefix: "UP", 59, 140
    )

    assert result["stats"]["skipped_windows"] > 0


def test_reject_short_training():
    with pytest.raises(ValueError):
        walk_forward(
            sample(),
            initial_train=50,
            cache_factory=FakeCache,
        )


def test_reject_small_test_window():
    with pytest.raises(ValueError):
        walk_forward(
            sample(),
            test_size=10,
            cache_factory=FakeCache,
        )


def test_reject_low_minimum_training_trades():
    with pytest.raises(ValueError):
        walk_forward(
            sample(),
            min_training_trades=5,
            cache_factory=FakeCache,
        )


def test_reject_duplicate_timestamps():
    df = sample()
    df.loc[100, "timestamp"] = df.loc[99, "timestamp"]

    with pytest.raises(ValueError):
        walk_forward(df, cache_factory=FakeCache)
