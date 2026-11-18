"""Exact forex session-aware historical request planning.

Dry-run only. Does not fetch data or execute trades.
"""

from dataclasses import dataclass

import pandas as pd

from market_data.session_batch_planner import plan_session_batches
from market_data.twelve_data_client import INTERVAL_SECONDS


@dataclass(frozen=True)
class ExactCollectionPlan:
    start_utc: pd.Timestamp
    end_utc: pd.Timestamp
    expected_candles: int
    planned_requests: int
    requests_this_run: int
    remaining_requests: int
    batch_candles: int
    analysis_only: bool = True


def create_exact_collection_plan(
    *,
    start,
    end,
    interval="1min",
    batch_candles=400,
    max_requests=5,
):
    if interval not in INTERVAL_SECONDS:
        raise ValueError("Unsupported interval")

    if type(batch_candles) is not int or not 2 <= batch_candles <= 4999:
        raise ValueError("Invalid batch_candles")

    if type(max_requests) is not int or max_requests < 1:
        raise ValueError("Invalid max_requests")

    start = pd.Timestamp(start)
    end = pd.Timestamp(end)

    if start.tzinfo is None or end.tzinfo is None:
        raise ValueError("Timezone-aware timestamps required")

    start = start.tz_convert("UTC")
    end = end.tz_convert("UTC")

    if start >= end:
        raise ValueError("Invalid collection window")

    step = pd.Timedelta(seconds=INTERVAL_SECONDS[interval])

    if start.value % step.value or end.value % step.value:
        raise ValueError("Collection boundaries must align to interval")

    batches = plan_session_batches(
        start=start,
        end=end,
        interval=interval,
        batch_candles=batch_candles,
    )

    expected_candles = sum(
        int((batch_end - batch_start) / step)
        for batch_start, batch_end in batches
    )

    planned_requests = len(batches)
    requests_this_run = min(planned_requests, max_requests)

    return ExactCollectionPlan(
        start_utc=start,
        end_utc=end,
        expected_candles=expected_candles,
        planned_requests=planned_requests,
        requests_this_run=requests_this_run,
        remaining_requests=planned_requests - requests_this_run,
        batch_candles=batch_candles,
    )
