
import pandas as pd
import pytest

from patterns import detect_candlestick_patterns


def candles(rows):
    return pd.DataFrame(
        rows,
        columns=["Open", "High", "Low", "Close"]
    )


def test_doji():
    data = candles([(10.0, 11.0, 9.0, 10.05)])
    result = detect_candlestick_patterns(data)
    assert "Doji" in result.loc[0, "Pattern"]


def test_hammer():
    data = candles([(10.0, 10.3, 8.0, 10.2)])
    result = detect_candlestick_patterns(data)
    assert "Hammer" in result.loc[0, "Pattern"]


def test_shooting_star():
    data = candles([(10.0, 12.0, 9.9, 10.1)])
    result = detect_candlestick_patterns(data)
    assert "Shooting Star" in result.loc[0, "Pattern"]


def test_bullish_engulfing():
    data = candles([
        (10.0, 10.1, 8.9, 9.0),
        (8.8, 10.5, 8.7, 10.2)
    ])
    result = detect_candlestick_patterns(data)
    assert "Bullish Engulfing" in result.loc[1, "Pattern"]


def test_bearish_engulfing():
    data = candles([
        (9.0, 10.1, 8.9, 10.0),
        (10.2, 10.3, 8.5, 8.8)
    ])
    result = detect_candlestick_patterns(data)
    assert "Bearish Engulfing" in result.loc[1, "Pattern"]


def test_bullish_harami():
    data = candles([
        (10.0, 10.1, 7.9, 8.0),
        (8.5, 9.2, 8.4, 9.0)
    ])
    result = detect_candlestick_patterns(data)
    assert "Bullish Harami" in result.loc[1, "Pattern"]


def test_bearish_harami():
    data = candles([
        (8.0, 10.1, 7.9, 10.0),
        (9.5, 9.6, 8.8, 9.0)
    ])
    result = detect_candlestick_patterns(data)
    assert "Bearish Harami" in result.loc[1, "Pattern"]


def test_morning_star():
    data = candles([
        (12.0, 12.1, 9.8, 10.0),
        (9.9, 10.1, 9.7, 9.85),
        (9.9, 11.5, 9.8, 11.2)
    ])
    result = detect_candlestick_patterns(data)
    assert "Morning Star" in result.loc[2, "Pattern"]


def test_evening_star():
    data = candles([
        (10.0, 12.2, 9.9, 12.0),
        (12.1, 12.3, 11.9, 12.15),
        (12.0, 12.1, 10.5, 10.8)
    ])
    result = detect_candlestick_patterns(data)
    assert "Evening Star" in result.loc[2, "Pattern"]


def test_invalid_ohlc():
    data = candles([(10.0, 9.0, 8.0, 10.5)])

    with pytest.raises(ValueError):
        detect_candlestick_patterns(data)


def test_missing_columns():
    data = pd.DataFrame({"Open": [1.0]})

    with pytest.raises(ValueError):
        detect_candlestick_patterns(data)


def test_input_is_not_modified():
    data = candles([(10.0, 10.4, 9.8, 10.2)])
    original = data.copy(deep=True)

    detect_candlestick_patterns(data)

    pd.testing.assert_frame_equal(data, original)

