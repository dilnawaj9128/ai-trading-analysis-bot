"""Offline-only, 15-minute historical price observation.

Candle timestamps represent candle OPEN times.
No API requests, future-dependent indicators or trading.
"""

import math

import pandas as pd


class HistoricalObservationError(ValueError):
    pass


def evaluate_historical_window(
    frame: pd.DataFrame,
    *,
    selected_index: int,
    expiry_minutes: int = 15,
):
    if type(expiry_minutes) is not int or expiry_minutes != 15:
        raise HistoricalObservationError(
            "Only 15-minute observation windows are supported"
        )

    if type(selected_index) is not int:
        raise HistoricalObservationError("Invalid selected_index")

    required = {"timestamp", "Open", "High", "Low", "Close"}
    if not isinstance(frame, pd.DataFrame) or not required.issubset(frame.columns):
        raise HistoricalObservationError("Valid OHLC DataFrame required")

    if selected_index < 0 or selected_index + 15 >= len(frame):
        raise HistoricalObservationError(
            "Insufficient future candles for a complete 15-minute window"
        )

    window = frame.iloc[selected_index:selected_index + 16].copy()

    # Require explicit timezone information.
    raw_times = window["timestamp"]
    if any(pd.Timestamp(value).tzinfo is None for value in raw_times):
        raise HistoricalObservationError("Timezone-aware timestamps required")

    times = pd.to_datetime(raw_times, utc=True, errors="raise")
    differences = times.diff().dropna()

    if not differences.eq(pd.Timedelta(minutes=1)).all():
        raise HistoricalObservationError(
            "Missing, duplicate or irregular candles in observation window"
        )

    for column in ("Open", "High", "Low", "Close"):
        values = pd.to_numeric(window[column], errors="raise")
        if not values.map(lambda value: math.isfinite(value) and value > 0).all():
            raise HistoricalObservationError("Invalid candle prices")
        window[column] = values

    if (
        (window["High"] < window[["Open", "Close", "Low"]].max(axis=1)).any()
        or (window["Low"] > window[["Open", "Close", "High"]].min(axis=1)).any()
    ):
        raise HistoricalObservationError("Invalid OHLC candle range")

    entry_close = float(window["Close"].iloc[0])
    exit_close = float(window["Close"].iloc[-1])
    movement = exit_close - entry_close

    direction = (
        "UP" if movement > 0
        else "DOWN" if movement < 0
        else "FLAT"
    )

    # No future rows are returned in the indicator input.
    available_at_observation = frame.iloc[:selected_index + 1].copy()

    return {
        "selected_index": selected_index,
        "observation_close_utc": (
            times.iloc[0] + pd.Timedelta(minutes=1)
        ).isoformat(),
        "evaluation_close_utc": (
            times.iloc[-1] + pd.Timedelta(minutes=1)
        ).isoformat(),
        "entry_close": entry_close,
        "exit_close": exit_close,
        "price_change": movement,
        "historical_direction": direction,
        "expiry_minutes": 15,
        "indicator_input": available_at_observation,
        "research_only": True,
        "prediction_generated": False,
        "execution_enabled": False,
    }
