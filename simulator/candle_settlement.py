
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import math

import pandas as pd


@dataclass(frozen=True)
class ExpiryPrice:
    price: float
    candle_time: datetime
    expiry_time: datetime
    source: str = "HISTORICAL_CANDLE"


def get_expiry_price(
    candles: pd.DataFrame,
    entry_time: datetime,
    expiry_minutes: int,
    retrieved_at: datetime,
) -> ExpiryPrice:
    """
    Find a historical 1-minute candle whose CLOSE boundary
    exactly matches the trade expiry.

    Assumptions:
    - Candle timestamps represent candle OPEN time.
    - Candles use UTC.
    - Only fully completed candles can be used.
    - No nearest-candle approximation is allowed.
    """

    if entry_time.tzinfo is None:
        raise ValueError("Entry time must be timezone-aware.")

    if retrieved_at.tzinfo is None:
        raise ValueError("Retrieval time must be timezone-aware.")

    if expiry_minutes not in (1, 5, 15):
        raise ValueError("Unsupported expiry duration.")

    if candles.empty:
        raise ValueError("No historical candles available.")

    required = {"timestamp", "Open", "High", "Low", "Close"}

    if not required.issubset(candles.columns):
        raise ValueError("Required OHLC columns are missing.")

    entry_time = entry_time.astimezone(timezone.utc)
    retrieved_at = retrieved_at.astimezone(timezone.utc)

    expiry_time = entry_time + timedelta(
        minutes=expiry_minutes
    )

    # This first implementation supports minute-aligned entries.
    if entry_time.second != 0 or entry_time.microsecond != 0:
        raise ValueError(
            "Entry must be aligned to a 1-minute boundary."
        )

    if retrieved_at < expiry_time:
        raise ValueError("Expiry candle is not completed yet.")

    data = candles.copy()

    data["timestamp"] = pd.to_datetime(
        data["timestamp"],
        utc=True,
        errors="raise",
    )

    target_open = expiry_time - timedelta(minutes=1)

    matching = data.loc[
        data["timestamp"] == pd.Timestamp(target_open)
    ]

    if len(matching) != 1:
        raise ValueError(
            "Exactly one matching expiry candle is required."
        )

    candle = matching.iloc[0]

    prices = [
        float(candle[column])
        for column in ("Open", "High", "Low", "Close")
    ]

    if not all(math.isfinite(price) and price > 0 for price in prices):
        raise ValueError("Invalid OHLC values.")

    open_price, high, low, close_price = prices

    if (
        high < low
        or high < max(open_price, close_price)
        or low > min(open_price, close_price)
    ):
        raise ValueError("Inconsistent OHLC values.")

    return ExpiryPrice(
        price=close_price,
        candle_time=target_open,
        expiry_time=expiry_time,
    )

