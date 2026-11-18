"""Audit historical candles against standard weekly FX sessions."""

import pandas as pd

from market_data.market_calendar import is_forex_market_open
from market_data.resumable_collector import validate_batch
from market_data.twelve_data_client import INTERVAL_SECONDS


def audit_forex_dataset(frame, *, start, end, interval="1min"):
    if interval not in INTERVAL_SECONDS:
        raise ValueError("Unsupported interval")

    start = pd.Timestamp(start)
    end = pd.Timestamp(end)

    if start.tzinfo is None or end.tzinfo is None:
        raise ValueError("Timezone-aware timestamps required")

    start = start.tz_convert("UTC")
    end = end.tz_convert("UTC")

    if start >= end:
        raise ValueError("Invalid time range")

    step = pd.Timedelta(seconds=INTERVAL_SECONDS[interval])

    data = validate_batch(frame, start, end, interval)

    expected = pd.date_range(
        start=start,
        end=end,
        freq=step,
        inclusive="left",
    )

    expected_open = pd.DatetimeIndex([
        stamp for stamp in expected
        if is_forex_market_open(stamp)
    ])

    actual = pd.DatetimeIndex(data["timestamp"])

    missing = expected_open.difference(actual)
    unexpected_closed = actual.difference(expected_open)

    return {
        "actual_candles": len(actual),
        "expected_open_candles": len(expected_open),
        "expected_closed_slots": len(expected) - len(expected_open),
        "missing_open_candles": len(missing),
        "unexpected_closed_candles": len(unexpected_closed),
        "first_missing": (
            missing[0].isoformat() if len(missing) else None
        ),
        "complete": (
            len(missing) == 0
            and len(unexpected_closed) == 0
        ),
    }
