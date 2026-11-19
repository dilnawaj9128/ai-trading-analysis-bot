from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest

from scripts.run_stage47_lookahead_audit import (
    alter_future,
    check_signal_invariance,
    check_training_isolation,
    validate_frame,
)

START = datetime(2026, 11, 12, 10, tzinfo=timezone.utc)


def sample_frame():
    rows = []
    for i in range(120):
        price = 1.1 + i * 0.00001
        rows.append({
            "timestamp": START + timedelta(minutes=i),
            "Open": price,
            "High": price + 0.001,
            "Low": price - 0.001,
            "Close": price,
        })
    return pd.DataFrame(rows)


class SafeCache:
    def __init__(self, df):
        self.df = df

    def for_variant(self, variant):
        def signal(prefix):
            return (
                "UP" if float(prefix["Close"].iloc[-1]) > 1.1
                else "DOWN"
            )
        return signal


class LeakyCache:
    def __init__(self, df):
        self.df = df

    def for_variant(self, variant):
        def signal(prefix):
            # Deliberate bug: uses the full dataset's future close.
            return (
                "UP" if float(self.df["Close"].iloc[-1]) > 1.105
                else "DOWN"
            )
        return signal


def test_future_change_preserves_past():
    df = sample_frame()
    changed = alter_future(df, 80)

    assert changed.iloc[:81].equals(df.iloc[:81])
    assert changed["Close"].iloc[-1] != df["Close"].iloc[-1]


def test_safe_signal_passes():
    checks = check_signal_invariance(
        sample_frame(), 80,
        variants=("safe",),
        cache_factory=SafeCache,
    )
    assert checks[0]["passed"] is True


def test_future_leak_detected():
    checks = check_signal_invariance(
        sample_frame(), 80,
        variants=("leaky",),
        cache_factory=LeakyCache,
    )
    assert checks[0]["passed"] is False


def test_bad_cutoff_rejected():
    with pytest.raises(ValueError, match="cutoff"):
        alter_future(sample_frame(), -1)


def test_too_early_checkpoint_rejected():
    with pytest.raises(ValueError, match="warmup"):
        check_signal_invariance(
            sample_frame(), 10,
            variants=("safe",),
            cache_factory=SafeCache,
        )


def test_naive_timestamps_rejected():
    df = sample_frame()
    df["timestamp"] = df["timestamp"].dt.tz_localize(None)

    with pytest.raises(ValueError, match="timestamps"):
        validate_frame(df)


def test_gap_rejected():
    df = sample_frame()
    df.loc[60:, "timestamp"] += timedelta(minutes=1)

    with pytest.raises(ValueError, match="Noncontiguous"):
        validate_frame(df)


def test_training_selection_isolated():
    df = sample_frame()

    def scorer(frame, signal_fn, start, end, payout):
        return {
            "stats": {
                "resolved": 40,
                "score": float(frame["Close"].iloc[end - 1]),
            }
        }

    def selector(scores, minimum_resolved):
        return "safe" if scores["safe"]["resolved"] >= minimum_resolved else None

    result = check_training_isolation(
        df, 80,
        variants=("safe",),
        cache_factory=SafeCache,
        scorer=scorer,
        selector=selector,
    )
    assert result["passed"] is True


def test_training_future_leak_detected():
    df = sample_frame()

    def leaky_scorer(frame, signal_fn, start, end, payout):
        return {"stats": {"score": float(frame["Close"].iloc[-1])}}

    def selector(scores, minimum_resolved):
        return "safe"

    result = check_training_isolation(
        df, 80,
        variants=("safe",),
        cache_factory=SafeCache,
        scorer=leaky_scorer,
        selector=selector,
    )
    assert result["passed"] is False
    assert "safe" in result["training_score_mismatches"]
