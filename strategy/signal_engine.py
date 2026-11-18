
from strategy.trend_analysis import analyze_trend
from strategy.market_filter import analyze_market_conditions


def generate_signal(
    data,
    expiry_minutes=15,
    data_mode="unknown",
    data_quality_status="INVALID",
):
    """
    Generate an explainable, analysis-only signal.

    Directional analysis is allowed only when:
    - Feed mode is explicitly live or delayed.
    - Data quality status is VALID.
    - At least 50 candles are available.

    Expiry is informational, not a prediction or guarantee.
    """

    if expiry_minutes not in (1, 5, 15):
        raise ValueError("expiry_minutes must be 1, 5, or 15.")

    mode = str(data_mode).strip().lower()
    quality_status = str(data_quality_status).strip().upper()

    def no_trade(reason, trend="UNKNOWN", momentum="UNKNOWN",
                 volatility="UNKNOWN", atr_percent=None):
        return {
            "signal": "NO TRADE",
            "trend": trend,
            "momentum": momentum,
            "volatility": volatility,
            "atr_percent": atr_percent,
            "expiry_minutes": expiry_minutes,
            "reasons": [reason],
        }

    # Safety gate 1: data quality
    if quality_status != "VALID":
        return no_trade(
            f"Data quality is {quality_status}; directional analysis blocked."
        )

    # Safety gate 2: verified feed mode
    if mode not in {"live", "delayed"}:
        return no_trade(
            "Data feed mode is unknown or unsupported. "
            "Verify the provider's feed mode before directional analysis."
        )

    # Safety gate 3: sufficient candles
    if data is None or len(data) < 50:
        return no_trade(
            "At least 50 candles are required."
        )

    row = data.iloc[-1]

    trend_result = analyze_trend(row)
    market_result = analyze_market_conditions(row)

    reasons = [
        trend_result["reason"],
        market_result["reason"],
    ]

    def filtered_no_trade(reason):
        return {
            "signal": "NO TRADE",
            "trend": trend_result["trend"],
            "momentum": market_result["momentum"],
            "volatility": market_result["volatility"],
            "atr_percent": market_result["atr_percent"],
            "expiry_minutes": expiry_minutes,
            "reasons": reasons + [reason],
        }

    if trend_result["trend"] == "UNKNOWN":
        return filtered_no_trade(
            "Trend could not be determined."
        )

    if not market_result["valid"]:
        return filtered_no_trade(
            market_result["reason"]
        )

    trend = trend_result["trend"]
    momentum = market_result["momentum"]

    if trend == "SIDEWAYS":
        return filtered_no_trade(
            "Sideways market: no clear trend."
        )

    if trend != momentum:
        return filtered_no_trade(
            "Trend and momentum are not aligned."
        )

    rsi = float(row["RSI_14"])

    if trend == "BULLISH" and rsi >= 70:
        return filtered_no_trade(
            "RSI is in the overbought zone."
        )

    if trend == "BEARISH" and rsi <= 30:
        return filtered_no_trade(
            "RSI is in the oversold zone."
        )

    # Check conflicting candlestick patterns.
    pattern_direction = str(
        row.get("Pattern_Direction", "NONE")
    ).upper()

    directions = {
        item.strip()
        for item in pattern_direction.split(";")
    }

    if "BULLISH" in directions and "BEARISH" in directions:
        return filtered_no_trade(
            "Conflicting candlestick patterns detected."
        )

    if trend == "BULLISH" and "BEARISH" in directions:
        return filtered_no_trade(
            "Bearish candlestick pattern conflicts with trend."
        )

    if trend == "BEARISH" and "BULLISH" in directions:
        return filtered_no_trade(
            "Bullish candlestick pattern conflicts with trend."
        )

    # Avoid signals immediately next to opposing S/R levels.
    atr = float(row["ATR_14"])
    close = float(row["Close"])

    for column in ("Support", "Resistance"):
        try:
            level = float(row[column])
        except (KeyError, TypeError, ValueError):
            level = None

        if level is not None:
            if trend == "BULLISH" and column == "Resistance":
                if abs(level - close) <= 0.25 * atr:
                    return filtered_no_trade(
                        "Price is too close to resistance."
                    )

            if trend == "BEARISH" and column == "Support":
                if abs(close - level) <= 0.25 * atr:
                    return filtered_no_trade(
                        "Price is too close to support."
                    )

    signal = "UP" if trend == "BULLISH" else "DOWN"

    reasons.append(
        "Trend, momentum and pattern checks are aligned."
    )

    if mode == "delayed":
        reasons.append(
            "WARNING: Analysis uses delayed market data."
        )

    reasons.append(
        "This is an analysis result, not a guaranteed prediction."
    )

    return {
        "signal": signal,
        "trend": trend,
        "momentum": momentum,
        "volatility": market_result["volatility"],
        "atr_percent": market_result["atr_percent"],
        "expiry_minutes": expiry_minutes,
        "reasons": reasons,
    }

