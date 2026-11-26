"""Fail-closed quality gate for 1-minute research candles."""

from datetime import datetime, timezone
import math

import pandas as pd


def validate_live_frame(frame, *, now=None):
    if not isinstance(frame, pd.DataFrame):
        raise ValueError("Expected DataFrame")

    required = {"timestamp", "Open", "High", "Low", "Close"}

    if not required.issubset(frame.columns):
        raise ValueError("Missing OHLC columns")

    if len(frame) < 60:
        raise ValueError("At least 60 candles required")

    now = datetime.now(timezone.utc) if now is None else now

    if not isinstance(now, datetime) or now.tzinfo is None:
        raise ValueError("Timezone-aware clock required")

    now = now.astimezone(timezone.utc)

    clean = frame[
        ["timestamp", "Open", "High", "Low", "Close"]
    ].copy()

    timestamps = pd.to_datetime(
        clean["timestamp"], utc=True, errors="raise"
    )

    if timestamps.isna().any():
        raise ValueError("Invalid timestamps")

    if timestamps.duplicated().any():
        raise ValueError("Duplicate candles")

    if not timestamps.is_monotonic_increasing:
        raise ValueError("Out-of-order candles")

    if (
        timestamps.diff().dropna()
        != pd.Timedelta(minutes=1)
    ).any():
        raise ValueError("Missing candle intervals")

    if (
        timestamps.dt.second.ne(0)
        | timestamps.dt.microsecond.ne(0)
    ).any():
        raise ValueError("Non-aligned candle timestamp")

    for column in ("Open", "High", "Low", "Close"):
        clean[column] = pd.to_numeric(
            clean[column], errors="raise"
        )

        if not clean[column].map(
            lambda value: math.isfinite(value) and value > 0
        ).all():
            raise ValueError("Invalid OHLC price")

    if not (
        clean["High"]
        >= clean[["Open", "Low", "Close"]].max(axis=1)
    ).all():
        raise ValueError("Invalid high")

    if not (
        clean["Low"]
        <= clean[["Open", "High", "Close"]].min(axis=1)
    ).all():
        raise ValueError("Invalid low")

    # Candle timestamps represent opening times.
    last_close = timestamps.iloc[-1].to_pydatetime()
    last_close += pd.Timedelta(minutes=1)

    age = (now - last_close).total_seconds()

    if age < 0:
        raise ValueError("Last candle is incomplete")

    if age > 180:
        raise ValueError("Stale market data")

    clean["timestamp"] = timestamps

    return {
        "frame": clean,
        "age_seconds": round(age, 2),
        "candles": len(clean),
        "quality": "VALID",
        "feed_verified": False,
        "analysis_only": True,
        "execution_enabled": False,
    }
