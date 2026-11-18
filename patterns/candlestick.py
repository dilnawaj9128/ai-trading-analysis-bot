
"""Rule-based candlestick pattern detection."""

import numpy as np
import pandas as pd

REQUIRED_COLUMNS = {"Open", "High", "Low", "Close"}


def validate_ohlc(data):
    missing = REQUIRED_COLUMNS - set(data.columns)

    if missing:
        raise ValueError(
            f"Missing required OHLC columns: {sorted(missing)}"
        )

    if data.empty:
        raise ValueError("OHLC data cannot be empty")

    values = data[["Open", "High", "Low", "Close"]].apply(
        pd.to_numeric, errors="coerce"
    )

    if not np.isfinite(values.to_numpy(dtype=float)).all():
        raise ValueError("OHLC values must be finite numbers")

    invalid = (
        (values["High"] < values[["Open", "Close", "Low"]].max(axis=1))
        | (values["Low"] > values[["Open", "Close", "High"]].min(axis=1))
    )

    if invalid.any():
        raise ValueError("Invalid OHLC candle range detected")

    return values


def detect_candlestick_patterns(data):
    """
    Detect nine common candlestick patterns.

    Input must contain completed candles.
    Returns a copy with pattern information.
    """

    values = validate_ohlc(data)
    result = data.copy()

    for column in REQUIRED_COLUMNS:
        result[column] = values[column]

    body = (values["Close"] - values["Open"]).abs()

    candle_range = (
        values["High"] - values["Low"]
    ).replace(0, np.nan)

    upper_shadow = (
        values["High"] -
        values[["Open", "Close"]].max(axis=1)
    )

    lower_shadow = (
        values[["Open", "Close"]].min(axis=1) -
        values["Low"]
    )

    body_ratio = body / candle_range

    bullish = values["Close"] > values["Open"]
    bearish = values["Close"] < values["Open"]

    detected = [[] for _ in range(len(values))]

    def add(i, name, direction, description):
        detected[i].append(
            (name, direction, description)
        )

    # 1. Doji
    for i in range(len(values)):

        if (
            pd.notna(body_ratio.iloc[i])
            and body_ratio.iloc[i] <= 0.10
        ):
            add(
                i,
                "Doji",
                "NEUTRAL",
                "Very small real body compared with candle range."
            )

    # 2. Hammer
    for i in range(len(values)):

        if (
            body.iloc[i] > 0
            and body_ratio.iloc[i] <= 0.35
            and lower_shadow.iloc[i] >= 2 * body.iloc[i]
            and upper_shadow.iloc[i] <= max(
                body.iloc[i] * 0.5,
                candle_range.iloc[i] * 0.10
            )
        ):
            add(
                i,
                "Hammer",
                "BULLISH",
                "Small body with a long lower shadow."
            )

    # 3. Shooting Star
    for i in range(len(values)):

        if (
            body.iloc[i] > 0
            and body_ratio.iloc[i] <= 0.35
            and upper_shadow.iloc[i] >= 2 * body.iloc[i]
            and lower_shadow.iloc[i] <= max(
                body.iloc[i] * 0.5,
                candle_range.iloc[i] * 0.10
            )
        ):
            add(
                i,
                "Shooting Star",
                "BEARISH",
                "Small body with a long upper shadow."
            )

    # Two-candle patterns
    for i in range(1, len(values)):

        previous_open = values["Open"].iloc[i - 1]
        previous_close = values["Close"].iloc[i - 1]

        current_open = values["Open"].iloc[i]
        current_close = values["Close"].iloc[i]

        previous_body = body.iloc[i - 1]
        current_body = body.iloc[i]

        # 4. Bullish Engulfing
        if (
            bearish.iloc[i - 1]
            and bullish.iloc[i]
            and current_open <= previous_close
            and current_close >= previous_open
            and current_body > 0
        ):
            add(
                i,
                "Bullish Engulfing",
                "BULLISH",
                "Bullish body engulfs previous bearish body."
            )

        # 5. Bearish Engulfing
        if (
            bullish.iloc[i - 1]
            and bearish.iloc[i]
            and current_open >= previous_close
            and current_close <= previous_open
            and current_body > 0
        ):
            add(
                i,
                "Bearish Engulfing",
                "BEARISH",
                "Bearish body engulfs previous bullish body."
            )

        previous_low = min(previous_open, previous_close)
        previous_high = max(previous_open, previous_close)

        contained = (
            current_open >= previous_low
            and current_open <= previous_high
            and current_close >= previous_low
            and current_close <= previous_high
            and current_body < previous_body
        )

        # 6. Bullish Harami
        if (
            contained
            and bearish.iloc[i - 1]
            and bullish.iloc[i]
        ):
            add(
                i,
                "Bullish Harami",
                "BULLISH",
                "Small bullish body inside previous bearish body."
            )

        # 7. Bearish Harami
        if (
            contained
            and bullish.iloc[i - 1]
            and bearish.iloc[i]
        ):
            add(
                i,
                "Bearish Harami",
                "BEARISH",
                "Small bearish body inside previous bullish body."
            )

    # Three-candle patterns
    for i in range(2, len(values)):

        first_midpoint = (
            values["Open"].iloc[i - 2]
            + values["Close"].iloc[i - 2]
        ) / 2

        middle_is_small = (
            body.iloc[i - 1] <= body.iloc[i - 2] * 0.5
        )

        # 8. Morning Star
        if (
            bearish.iloc[i - 2]
            and middle_is_small
            and bullish.iloc[i]
            and values["Close"].iloc[i] > first_midpoint
            and body.iloc[i] > 0
        ):
            add(
                i,
                "Morning Star",
                "BULLISH",
                "Three-candle bullish reversal structure."
            )

        # 9. Evening Star
        if (
            bullish.iloc[i - 2]
            and middle_is_small
            and bearish.iloc[i]
            and values["Close"].iloc[i] < first_midpoint
            and body.iloc[i] > 0
        ):
            add(
                i,
                "Evening Star",
                "BEARISH",
                "Three-candle bearish reversal structure."
            )

    result["Pattern"] = [
        "; ".join(item[0] for item in row) if row else "None"
        for row in detected
    ]

    result["Pattern_Direction"] = [
        "; ".join(dict.fromkeys(item[1] for item in row))
        if row else "NONE"
        for row in detected
    ]

    result["Pattern_Description"] = [
        " ".join(item[2] for item in row)
        if row else "No recognized pattern."
        for row in detected
    ]

    return result

