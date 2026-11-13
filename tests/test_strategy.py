
import pandas as pd
import pytest

from strategy import generate_signal


def make_data(
    close=1.2,
    ema20=1.1,
    ema50=1.0,
    rsi=60,
    macd=0.001,
    pattern="NONE",
    support=0.9,
    resistance=1.5,
):
    return pd.DataFrame({
        "Close": [close] * 50,
        "EMA_20": [ema20] * 50,
        "EMA_50": [ema50] * 50,
        "RSI_14": [rsi] * 50,
        "MACD_histogram": [macd] * 50,
        "ATR_14": [0.01] * 50,
        "Pattern_Direction": [pattern] * 50,
        "Support": [support] * 50,
        "Resistance": [resistance] * 50,
    })


def valid_signal(data, **kwargs):
    """Helper for explicitly verified test data."""
    return generate_signal(
        data,
        data_mode="live",
        data_quality_status="VALID",
        **kwargs,
    )


# Existing strategy tests

def test_bullish_signal():
    result = valid_signal(make_data())
    assert result["signal"] == "UP"


def test_bearish_signal():
    data = make_data(
        close=0.8,
        ema20=0.9,
        ema50=1.0,
        rsi=40,
        macd=-0.001,
        support=0.5,
        resistance=1.2,
    )

    result = valid_signal(data)
    assert result["signal"] == "DOWN"


def test_sideways_market_returns_no_trade():
    data = make_data(ema20=1.2, ema50=1.0)

    result = valid_signal(data)
    assert result["signal"] == "NO TRADE"


def test_conflicting_momentum_returns_no_trade():
    data = make_data(macd=-0.001)

    result = valid_signal(data)
    assert result["signal"] == "NO TRADE"


def test_opposite_pattern_returns_no_trade():
    data = make_data(pattern="BEARISH")

    result = valid_signal(data)
    assert result["signal"] == "NO TRADE"


def test_insufficient_candles_returns_no_trade():
    data = make_data().head(20)

    result = valid_signal(data)
    assert result["signal"] == "NO TRADE"


def test_invalid_expiry_is_rejected():
    with pytest.raises(ValueError):
        valid_signal(make_data(), expiry_minutes=10)


def test_fifteen_minute_expiry_is_preserved():
    result = valid_signal(
        make_data(),
        expiry_minutes=15,
    )

    assert result["expiry_minutes"] == 15


# New safety tests

def test_unknown_feed_mode_returns_no_trade():
    result = generate_signal(
        make_data(),
        data_mode="unknown",
        data_quality_status="VALID",
    )

    assert result["signal"] == "NO TRADE"
    assert any(
        "feed mode is unknown" in reason.lower()
        for reason in result["reasons"]
    )


def test_simulated_feed_mode_returns_no_trade():
    result = generate_signal(
        make_data(),
        data_mode="simulated",
        data_quality_status="VALID",
    )

    assert result["signal"] == "NO TRADE"


def test_invalid_data_quality_returns_no_trade():
    result = generate_signal(
        make_data(),
        data_mode="live",
        data_quality_status="INVALID",
    )

    assert result["signal"] == "NO TRADE"
    assert any(
        "data quality is invalid" in reason.lower()
        for reason in result["reasons"]
    )


def test_stale_data_returns_no_trade():
    result = generate_signal(
        make_data(),
        data_mode="live",
        data_quality_status="STALE",
    )

    assert result["signal"] == "NO TRADE"
    assert any(
        "data quality is stale" in reason.lower()
        for reason in result["reasons"]
    )


def test_delayed_feed_adds_warning():
    result = generate_signal(
        make_data(),
        data_mode="delayed",
        data_quality_status="VALID",
    )

    assert result["signal"] == "UP"
    assert any(
        "delayed market data" in reason.lower()
        for reason in result["reasons"]
    )

