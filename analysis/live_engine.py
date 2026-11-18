
"""Research-only technical analysis of validated completed candles."""

import pandas as pd

from indicators import calculate_ema, calculate_indicators
from patterns.candlestick import detect_candlestick_patterns


def analyze_live_candles(frame: pd.DataFrame) -> dict:
    """Analyze completed OHLC candles without placing trades."""

    if not isinstance(frame, pd.DataFrame):
        raise TypeError("Expected pandas DataFrame")

    if len(frame) < 60:
        raise ValueError(
            "At least 60 completed candles are required"
        )

    # Existing validation and indicators are reused.
    enriched = calculate_indicators(frame)

    enriched["EMA_9"] = calculate_ema(
        enriched["Close"], 9
    )
    enriched["EMA_21"] = calculate_ema(
        enriched["Close"], 21
    )

    patterns = detect_candlestick_patterns(frame)

    latest = enriched.iloc[-1]

    ema9 = latest["EMA_9"]
    ema21 = latest["EMA_21"]
    rsi = latest["RSI_14"]

    observations = []

    if pd.notna(ema9) and pd.notna(ema21):
        if ema9 > ema21:
            observations.append(
                "Short-term EMA 9 is above EMA 21"
            )
        elif ema9 < ema21:
            observations.append(
                "Short-term EMA 9 is below EMA 21"
            )
        else:
            observations.append(
                "EMA 9 and EMA 21 are equal"
            )

    if pd.notna(rsi):
        if rsi > 70:
            observations.append(
                "RSI is above 70 (high momentum reading)"
            )
        elif rsi < 30:
            observations.append(
                "RSI is below 30 (low momentum reading)"
            )
        else:
            observations.append(
                "RSI is between 30 and 70"
            )

    return {
        "frame": enriched,
        "patterns": patterns,
        "observations": observations,
        "latest": latest.to_dict(),
        "analysis_only": True,
        "execution_enabled": False,
        "directional_backtesting_allowed": False,
    }

