"""Conservative market-closure checks for research datasets."""

import pandas as pd


def is_full_saturday_utc(start, end):
    """True only when every minute in [start, end) is Saturday UTC."""
    start = pd.Timestamp(start)
    end = pd.Timestamp(end)

    if start.tzinfo is None or end.tzinfo is None:
        raise ValueError("Timezone-aware timestamps required")

    start = start.tz_convert("UTC")
    end = end.tz_convert("UTC")

    if start >= end:
        raise ValueError("Invalid time window")

    last = end - pd.Timedelta(nanoseconds=1)

    return (
        start.weekday() == 5
        and last.weekday() == 5
    )


def is_forex_market_open(timestamp):
    """Standard weekly FX session, using New York local time.

    This is a calendar approximation, not a guarantee of
    Twelve Data provider availability or holiday schedules.
    """
    stamp = pd.Timestamp(timestamp)

    if stamp.tzinfo is None:
        raise ValueError("Timezone-aware timestamp required")

    ny = stamp.tz_convert("America/New_York")
    weekday = ny.weekday()
    hour = ny.hour

    if weekday == 5:
        return False

    if weekday == 6:
        return hour >= 17

    if weekday == 4:
        return hour < 17

    return True


def is_full_forex_closure(start, end, interval="1min"):
    """True only when every candle slot is outside weekly FX hours."""
    from market_data.twelve_data_client import INTERVAL_SECONDS

    if interval not in INTERVAL_SECONDS:
        raise ValueError("Unsupported interval")

    start = pd.Timestamp(start)
    end = pd.Timestamp(end)

    if start.tzinfo is None or end.tzinfo is None:
        raise ValueError("Timezone-aware timestamps required")

    if start >= end:
        raise ValueError("Invalid window")

    step = pd.Timedelta(seconds=INTERVAL_SECONDS[interval])

    slots = pd.date_range(
        start=start,
        end=end,
        freq=step,
        inclusive="left",
    )

    return bool(len(slots)) and all(
        not is_forex_market_open(stamp)
        for stamp in slots
    )


def split_forex_open_windows(start, end, interval="1min"):
    """Return contiguous weekly-FX-open windows as half-open ranges.

    This is a standard weekly-session approximation, not a
    provider-specific holiday or market-hours guarantee.
    """
    from market_data.twelve_data_client import INTERVAL_SECONDS

    if interval not in INTERVAL_SECONDS:
        raise ValueError("Unsupported interval")

    start = pd.Timestamp(start)
    end = pd.Timestamp(end)

    if start.tzinfo is None or end.tzinfo is None:
        raise ValueError("Timezone-aware timestamps required")

    start = start.tz_convert("UTC")
    end = end.tz_convert("UTC")

    if start >= end:
        raise ValueError("Invalid window")

    step = pd.Timedelta(seconds=INTERVAL_SECONDS[interval])

    if start != start.floor(step) or end != end.floor(step):
        raise ValueError("Window boundaries must align to interval")

    segments = []
    segment_start = None

    for stamp in pd.date_range(
        start=start,
        end=end,
        freq=step,
        inclusive="left",
    ):
        if is_forex_market_open(stamp):
            if segment_start is None:
                segment_start = stamp
        elif segment_start is not None:
            segments.append((segment_start, stamp))
            segment_start = None

    if segment_start is not None:
        segments.append((segment_start, end))

    return segments
