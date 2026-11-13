
import numpy as np
import pandas as pd
import pytest

from analysis.live_engine import analyze_live_candles


def make_candles(n=120):
    close = np.linspace(100, 110, n)

    return pd.DataFrame({
        "Open": close - 0.1,
        "High": close + 0.5,
        "Low": close - 0.5,
        "Close": close,
    })


def test_live_engine_returns_indicators():
    result = analyze_live_candles(make_candles())

    frame = result["frame"]

    assert "EMA_9" in frame.columns
    assert "EMA_21" in frame.columns
    assert "RSI_14" in frame.columns
    assert "MACD" in frame.columns


def test_live_engine_is_analysis_only():
    result = analyze_live_candles(make_candles())

    assert result["analysis_only"] is True
    assert result["execution_enabled"] is False
    assert result["directional_backtesting_allowed"] is False


def test_insufficient_candles_rejected():
    with pytest.raises(ValueError):
        analyze_live_candles(make_candles(30))


def test_observations_available():
    result = analyze_live_candles(make_candles())

    assert isinstance(result["observations"], list)
    assert len(result["observations"]) > 0


def test_original_dataframe_unchanged():
    original = make_candles()
    before = original.copy(deep=True)

    analyze_live_candles(original)

    pd.testing.assert_frame_equal(original, before)

