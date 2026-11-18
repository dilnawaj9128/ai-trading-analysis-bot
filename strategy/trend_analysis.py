
def analyze_trend(row):
    """Classify market trend using price and EMA alignment."""

    required = ["Close", "EMA_20", "EMA_50"]

    for column in required:
        value = row.get(column)

        if value is None or not _is_finite(value):
            return {
                "trend": "UNKNOWN",
                "reason": f"Missing or invalid {column} value."
            }

    close = float(row["Close"])
    ema_20 = float(row["EMA_20"])
    ema_50 = float(row["EMA_50"])

    if close > ema_20 > ema_50:
        return {
            "trend": "BULLISH",
            "reason": "Price is above EMA 20 and EMA 20 is above EMA 50."
        }

    if close < ema_20 < ema_50:
        return {
            "trend": "BEARISH",
            "reason": "Price is below EMA 20 and EMA 20 is below EMA 50."
        }

    return {
        "trend": "SIDEWAYS",
        "reason": "Price and EMA alignment do not confirm a clear trend."
    }


def _is_finite(value):
    try:
        import math
        return math.isfinite(float(value))
    except (TypeError, ValueError):
        return False

