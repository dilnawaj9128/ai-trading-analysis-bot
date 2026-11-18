"""Historical data coverage analysis. No API calls."""

from dataclasses import dataclass

import pandas as pd

from market_data.market_calendar import is_forex_market_open


@dataclass(frozen=True)
class CoverageReport:
    actual_candles: int
    expected_candles: int
    missing_candles: int
    coverage_percent: float
    complete: bool


def analyze_coverage(
    frame: pd.DataFrame,
    *,
    start,
    end,
    interval="1min",
) -> CoverageReport:
    intervals = {
        "1min": "1min",
        "5min": "5min",
        "15min": "15min",
    }

    if interval not in intervals:
        raise ValueError("Unsupported interval")

    start = pd.Timestamp(start)
    end = pd.Timestamp(end)

    if start.tzinfo is None or end.tzinfo is None:
        raise ValueError("Timezone-aware boundaries required")

    start = start.tz_convert("UTC")
    end = end.tz_convert("UTC")

    if start >= end:
        raise ValueError("Invalid time range")

    if not isinstance(frame, pd.DataFrame):
        raise ValueError("DataFrame required")

    if "timestamp" not in frame.columns:
        raise ValueError("Missing timestamp column")

    timestamps = pd.to_datetime(
        frame["timestamp"],
        utc=True,
        errors="raise",
    )

    if timestamps.duplicated().any():
        raise ValueError("Duplicate timestamps")

    if ((timestamps < start) | (timestamps >= end)).any():
        raise ValueError("Timestamp outside requested range")

    expected = pd.date_range(
        start=start,
        end=end,
        freq=intervals[interval],
        inclusive="left",
    )

    expected_open = pd.DatetimeIndex([
        stamp
        for stamp in expected
        if is_forex_market_open(stamp)
    ])

    actual = pd.DatetimeIndex(timestamps)

    unexpected = actual.difference(expected_open)

    if len(unexpected):
        raise ValueError(
            "Unexpected or misaligned market-closed candles"
        )

    missing = expected_open.difference(actual)

    expected_count = len(expected_open)
    actual_count = len(actual)

    coverage = (
        100.0 * actual_count / expected_count
        if expected_count
        else 100.0
    )

    return CoverageReport(
        actual_candles=actual_count,
        expected_candles=expected_count,
        missing_candles=len(missing),
        coverage_percent=round(coverage, 2),
        complete=len(missing) == 0,
    )
