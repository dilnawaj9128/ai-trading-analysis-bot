
import math


def analyze_market_conditions(row):
    required = [
        "RSI_14",
        "MACD_histogram",
        "ATR_14",
        "Close",
    ]

    for column in required:
        try:
            value = float(row[column])
            if not math.isfinite(value):
                raise ValueError
        except (KeyError, TypeError, ValueError):
            return {
                "valid": False,
                "momentum": "UNKNOWN",
                "volatility": "UNKNOWN",
                "atr_percent": None,
                "reason": f"Missing or invalid {column}."
            }

    rsi = float(row["RSI_14"])
    macd_hist = float(row["MACD_histogram"])
    atr = float(row["ATR_14"])
    close = float(row["Close"])

    if close <= 0 or atr < 0 or not 0 <= rsi <= 100:
        return {
            "valid": False,
            "momentum": "UNKNOWN",
            "volatility": "UNKNOWN",
            "atr_percent": None,
            "reason": "Indicator values are outside valid ranges."
        }

    if rsi > 55 and macd_hist > 0:
        momentum = "BULLISH"
    elif rsi < 45 and macd_hist < 0:
        momentum = "BEARISH"
    else:
        momentum = "NEUTRAL"

    atr_percent = (atr / close) * 100

    return {
        "valid": True,
        "momentum": momentum,
        "volatility": "MEASURED",
        "atr_percent": atr_percent,
        "reason": (
            f"RSI={rsi:.2f}; MACD histogram={macd_hist:.8f}; "
            f"ATR={atr_percent:.5f}% of price."
        )
    }

