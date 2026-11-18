"""Technical indicator API for the AI market analysis bot."""
from .atr import calculate_atr
from .ema import calculate_ema
from .macd import calculate_macd
from .rsi import calculate_rsi
from .support_resistance import calculate_support_resistance
from .volatility import calculate_volatility


def calculate_indicators(df):
    """Return a copy of completed OHLC candles enriched with indicators.

    The caller must pass only validated, completed candles. Support/resistance
    is shifted by one candle so the current candle cannot leak into its levels.
    """
    from ._utils import validate_ohlc

    data = validate_ohlc(df)
    data["RSI_14"] = calculate_rsi(data["Close"], 14)
    data["EMA_20"] = calculate_ema(data["Close"], 20)
    data["EMA_50"] = calculate_ema(data["Close"], 50)
    macd = calculate_macd(data["Close"], 12, 26, 9)
    data = data.join(macd)
    data["ATR_14"] = calculate_atr(data, 14)
    data["Volatility_20_pct"] = calculate_volatility(data["Close"], 20)
    data = data.join(calculate_support_resistance(data, 20))
    return data


__all__ = [
    "calculate_atr", "calculate_ema", "calculate_macd", "calculate_rsi",
    "calculate_support_resistance", "calculate_volatility", "calculate_indicators",
]
