import numpy as np
import pandas as pd
import pytest

from indicators import (
    calculate_atr, calculate_ema, calculate_indicators, calculate_macd,
    calculate_rsi, calculate_support_resistance, calculate_volatility,
)


def sample_ohlc(n=60):
    close = pd.Series(np.linspace(1.10, 1.16, n))
    return pd.DataFrame({
        "Open": close - 0.0002,
        "High": close + 0.0010,
        "Low": close - 0.0010,
        "Close": close,
        "Volume": np.nan,
    })


def test_ema_known_values_and_warmup():
    result = calculate_ema(pd.Series([1.0, 2.0, 3.0]), period=3)
    assert result.iloc[:2].isna().all()
    assert result.iloc[2] == pytest.approx(2.25)


def test_rsi_rising_series_is_100_after_warmup():
    result = calculate_rsi(pd.Series(range(1, 17), dtype=float), period=14)
    assert result.iloc[:14].isna().all()
    assert result.iloc[14] == pytest.approx(100.0)
    assert result.iloc[15] == pytest.approx(100.0)


def test_rsi_flat_series_is_50():
    result = calculate_rsi(pd.Series([5.0] * 16), period=14)
    assert result.iloc[14] == pytest.approx(50.0)


def test_macd_columns_and_ordering():
    result = calculate_macd(pd.Series(np.linspace(1, 2, 60)))
    assert list(result.columns) == ["MACD", "MACD_signal", "MACD_histogram"]
    assert result["MACD"].notna().any()
    assert result["MACD_histogram"].dropna().iloc[-1] == pytest.approx(
        result["MACD"].dropna().iloc[-1] - result["MACD_signal"].dropna().iloc[-1]
    )


def test_atr_constant_range_is_two():
    data = pd.DataFrame({"High": [11.0] * 5, "Low": [9.0] * 5, "Close": [10.0] * 5})
    result = calculate_atr(data, period=3)
    assert result.iloc[:2].isna().all()
    assert result.iloc[2] == pytest.approx(2.0)
    assert result.iloc[-1] == pytest.approx(2.0)


def test_volatility_constant_returns_is_zero():
    result = calculate_volatility(pd.Series([10.0] * 10), period=3)
    assert result.dropna().eq(0.0).all()


def test_support_resistance_uses_only_previous_candles():
    data = sample_ohlc(25)
    original = calculate_support_resistance(data, window=5)
    changed = data.copy()
    changed.loc[5, "High"] = 99.0
    changed.loc[5, "Low"] = 0.01
    recalculated = calculate_support_resistance(changed, window=5)
    # Levels for candle 5 are based on candles 0..4, not candle 5 itself.
    assert recalculated.loc[5, "Resistance"] == pytest.approx(original.loc[5, "Resistance"])
    assert recalculated.loc[5, "Support"] == pytest.approx(original.loc[5, "Support"])


def test_aggregate_indicators_preserves_input_and_adds_columns():
    data = sample_ohlc(60)
    original = data.copy(deep=True)
    result = calculate_indicators(data)
    expected = {"RSI_14", "EMA_20", "EMA_50", "MACD", "MACD_signal", "MACD_histogram", "ATR_14", "Volatility_20_pct", "Support", "Resistance"}
    assert expected.issubset(result.columns)
    pd.testing.assert_frame_equal(data, original)


def test_invalid_period_raises():
    with pytest.raises(ValueError):
        calculate_ema(pd.Series([1.0, 2.0]), period=0)
