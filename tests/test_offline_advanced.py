"""Offline Stage 19D behavior: no provider calls and no look-ahead."""
import numpy as np
import pandas as pd
import pytest

from dashboard.offline_advanced import build_advanced_research


def make_frame(n=90):
    prices = 1.10 + np.arange(n) * 0.00002 + np.sin(np.arange(n) / 5) * 0.0001
    return pd.DataFrame({
        "timestamp": pd.date_range("2026-11-12 10:00", periods=n, freq="min", tz="UTC"),
        "Open": prices,
        "High": prices + 0.00025,
        "Low": prices - 0.00025,
        "Close": prices + 0.00003,
    })


def test_offline_advanced_contains_indicator_pattern_and_safety_fields():
    output = build_advanced_research(make_frame())
    assert {"EMA_20", "EMA_50", "RSI_14", "ATR_14", "MACD_histogram", "Support", "Resistance"} <= set(output["enriched"].columns)
    assert {"Pattern", "Pattern_Direction", "Pattern_Description"} <= set(output["patterns"].columns)
    assert output["action"] == "NO TRADE"
    assert output["analysis_only"] is True
    assert output["execution_enabled"] is False
    assert output["directional_backtesting_allowed"] is False


def test_does_not_mutate_source_and_indicators_have_no_future_leakage():
    original = make_frame(90)
    saved = original.copy(deep=True)
    current = build_advanced_research(original)
    pd.testing.assert_frame_equal(original, saved)
    # Appending future candles cannot change indicators on older rows.
    expanded = make_frame(100)
    future = build_advanced_research(expanded)
    for name in ("EMA_20", "EMA_50", "MACD_histogram", "ATR_14", "Support", "Resistance"):
        a = current["enriched"][name].reset_index(drop=True)
        b = future["enriched"][name].iloc[:90].reset_index(drop=True)
        pd.testing.assert_series_equal(a, b)


def test_rejects_too_short_dataset():
    with pytest.raises(ValueError, match="60"):
        build_advanced_research(make_frame(20))
