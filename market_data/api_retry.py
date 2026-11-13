"""Bounded API retry helper for historical research."""

import time

from market_data.twelve_data_client import (
    BudgetExceeded,
    MarketDataError,
)


def fetch_with_retry(
    fetcher,
    *,
    max_attempts=3,
    wait_seconds=65,
):
    """Retry only local minute-budget exhaustion.

    Daily exhaustion, provider errors, and network failures
    are not retried automatically.
    """
    if type(max_attempts) is not int or max_attempts < 1:
        raise ValueError("Invalid max_attempts")

    if not isinstance(wait_seconds, (int, float)) or wait_seconds < 0:
        raise ValueError("Invalid wait_seconds")

    for attempt in range(max_attempts):
        try:
            return fetcher()
        except BudgetExceeded as exc:
            if "minute budget" not in str(exc).lower():
                raise

            if attempt + 1 >= max_attempts:
                raise

            time.sleep(wait_seconds)

    raise MarketDataError("Retry attempts exhausted")
