"""Stage 19F read-only historical chart regression tests."""
import pandas as pd
import pytest

from analysis.historical_observation import evaluate_historical_window
from dashboard.historical_outcome_chart import build_historical_outcome_chart


def candles():
    n = 100
    return pd.DataFrame({
        "timestamp": pd.date_range("2026-11-12 10:00", periods=n, freq="min", tz="UTC"),
        "Open": [1.1] * n,
        "High": [1.2] * n,
        "Low": [1.0] * n,
        "Close": [1.1] * n,
    })


def test_historical_chart_has_candles_and_two_markers():
    frame = candles()
    obs = evaluate_historical_window(frame, selected_index=60)
    fig = build_historical_outcome_chart(frame, obs)
    assert len(fig.data) == 3
    assert len(fig.data[0].x) == 26  # 10 context, selected candle, 15 future
    assert fig.data[1].name == "Observation close"
    assert fig.data[2].name == "15-minute outcome close"


def test_chart_does_not_modify_source_or_indicator_input():
    frame = candles()
    original = frame.copy(deep=True)
    obs = evaluate_historical_window(frame, selected_index=60)
    before = obs["indicator_input"].copy(deep=True)
    build_historical_outcome_chart(frame, obs)
    pd.testing.assert_frame_equal(frame, original)
    pd.testing.assert_frame_equal(obs["indicator_input"], before)
    assert len(obs["indicator_input"]) == 61


def test_chart_rejects_incomplete_index():
    frame = candles()
    obs = evaluate_historical_window(frame, selected_index=60)
    obs["selected_index"] = 95
    with pytest.raises(ValueError):
        build_historical_outcome_chart(frame, obs)


def test_chart_rejects_wrong_evaluation_duration():
    frame = candles()
    obs = evaluate_historical_window(frame, selected_index=60)
    obs["evaluation_close_utc"] = obs["observation_close_utc"]
    with pytest.raises(ValueError):
        build_historical_outcome_chart(frame, obs)
