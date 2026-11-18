
"""
Stage 6.5 - Historical Data Integrity

Research-only validation for 1-minute OHLC datasets.

Assumptions:
- Candle timestamp = candle opening time
- Candle interval = [timestamp, timestamp + 1 minute)
- Historical entry at a minute boundary uses that candle's Open
- Expiry at a minute boundary uses the previous candle's Close

This does not verify Quotex or OTC execution prices.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import math

import pandas as pd


UTC = timezone.utc
ONE_MINUTE = timedelta(minutes=1)

ALLOWED_EXPIRIES = (1, 5, 15)
REQUIRED_COLUMNS = (
    "timestamp", "Open", "High", "Low", "Close"
)


@dataclass(frozen=True)
class HistoricalProvenance:
    provider: str
    feed_mode: str
    retrieved_at: datetime
    symbol: str = "EUR/USD"
    timeframe: str = "1min"


@dataclass(frozen=True)
class ValidatedHistoricalTrade:
    entry_price: float
    expiry_price: float
    entry_time: datetime
    expiry_time: datetime
    expiry_candle_time: datetime
    candle_count: int
    provenance: HistoricalProvenance
    classification: str = "HISTORICAL_RESEARCH"


def require_utc(value, field):
    if not isinstance(value, datetime):
        raise ValueError(f"{field} must be a datetime.")

    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field} must be timezone-aware.")

    return value.astimezone(UTC)


def require_minute_boundary(value, field):
    if value.second != 0 or value.microsecond != 0:
        raise ValueError(
            f"{field} must align to a minute boundary."
        )


def validate_provenance(provenance):
    if not isinstance(provenance, HistoricalProvenance):
        raise ValueError("Historical provenance is required.")

    if not isinstance(provenance.provider, str):
        raise ValueError("Provider must be a string.")

    if not provenance.provider.strip():
        raise ValueError("Provider name is required.")

    if not isinstance(provenance.feed_mode, str):
        raise ValueError("Feed mode must be a string.")

    if not provenance.feed_mode.strip():
        raise ValueError("Feed mode is required.")

    if provenance.feed_mode.strip().lower() == "unknown":
        raise ValueError(
            "Unknown feed mode cannot be used for "
            "historical settlement."
        )

    if provenance.timeframe != "1min":
        raise ValueError("Only 1-minute candles are supported.")

    if provenance.symbol != "EUR/USD":
        raise ValueError("Only EUR/USD is supported in this stage.")

    require_utc(provenance.retrieved_at, "retrieved_at")


def normalize_candles(candles):
    if not isinstance(candles, pd.DataFrame):
        raise ValueError("Candles must be a DataFrame.")

    if candles.empty:
        raise ValueError("Historical candles are empty.")

    if not set(REQUIRED_COLUMNS).issubset(candles.columns):
        raise ValueError("Required OHLC columns are missing.")

    data = candles.loc[:, REQUIRED_COLUMNS].copy()

    raw_timestamps = data["timestamp"]

    # Reject naive datetime values and timezone-free strings.
    for value in raw_timestamps:
        if isinstance(value, pd.Timestamp):
            aware = (
                value.tzinfo is not None
                and value.utcoffset() is not None
            )
        elif isinstance(value, datetime):
            aware = (
                value.tzinfo is not None
                and value.utcoffset() is not None
            )
        elif isinstance(value, str):
            try:
                parsed = datetime.fromisoformat(
                    value.replace("Z", "+00:00")
                )
                aware = (
                    parsed.tzinfo is not None
                    and parsed.utcoffset() is not None
                )
            except ValueError:
                aware = False
        else:
            aware = False

        if not aware:
            raise ValueError(
                "Every candle timestamp must include a timezone."
            )

    try:
        data["timestamp"] = pd.to_datetime(
            data["timestamp"],
            utc=True,
            errors="raise",
        )
    except (ValueError, TypeError) as exc:
        raise ValueError("Invalid candle timestamp.") from exc

    if data["timestamp"].isna().any():
        raise ValueError("Missing candle timestamp.")

    if data["timestamp"].duplicated().any():
        raise ValueError("Duplicate candle timestamp.")

    for timestamp in data["timestamp"]:
        require_minute_boundary(
            timestamp.to_pydatetime(),
            "Candle timestamp",
        )

    for column in ("Open", "High", "Low", "Close"):
        try:
            data[column] = pd.to_numeric(
                data[column],
                errors="raise",
            )
        except (ValueError, TypeError) as exc:
            raise ValueError(
                f"Invalid {column} value."
            ) from exc

        if not data[column].map(
            lambda value: (
                math.isfinite(float(value))
                and float(value) > 0
            )
        ).all():
            raise ValueError(
                f"{column} contains invalid prices."
            )

    if (
        (data["High"] < data["Low"]).any()
        or (
            data["High"]
            < data[["Open", "Close"]].max(axis=1)
        ).any()
        or (
            data["Low"]
            > data[["Open", "Close"]].min(axis=1)
        ).any()
    ):
        raise ValueError("Inconsistent OHLC candle values.")

    return data.sort_values("timestamp").reset_index(
        drop=True
    )


def validate_historical_trade(
    candles,
    entry_time,
    expiry_minutes,
    provenance,
    claimed_entry_price=None,
):
    """
    Validate a complete historical entry-to-expiry interval.

    The returned object is research-only.
    It does not execute or settle a trade in SQLite.
    """

    validate_provenance(provenance)

    entry_time = require_utc(entry_time, "entry_time")
    require_minute_boundary(entry_time, "entry_time")

    if expiry_minutes not in ALLOWED_EXPIRIES:
        raise ValueError("Expiry must be 1, 5, or 15 minutes.")

    expiry_time = entry_time + timedelta(
        minutes=expiry_minutes
    )

    retrieved_at = require_utc(
        provenance.retrieved_at,
        "retrieved_at",
    )

    if retrieved_at < expiry_time:
        raise ValueError(
            "Expiry interval is not fully completed."
        )

    data = normalize_candles(candles)

    # Select only candles needed for this historical trade.
    interval = data.loc[
        (data["timestamp"] >= pd.Timestamp(entry_time))
        & (data["timestamp"] < pd.Timestamp(expiry_time))
    ].copy()

    expected_times = pd.date_range(
        start=entry_time,
        periods=expiry_minutes,
        freq="min",
        tz="UTC",
    )

    actual_times = pd.DatetimeIndex(
        interval["timestamp"]
    )

    if not actual_times.equals(expected_times):
        raise ValueError(
            "Missing or unexpected candle in entry-expiry interval."
        )

    # Entry at exact candle OPEN boundary.
    entry_price = float(interval.iloc[0]["Open"])

    # Expiry at exact final candle CLOSE boundary.
    expiry_price = float(interval.iloc[-1]["Close"])

    if claimed_entry_price is not None:
        try:
            claimed = float(claimed_entry_price)
        except (TypeError, ValueError) as exc:
            raise ValueError(
                "Invalid claimed entry price."
            ) from exc

        if not math.isfinite(claimed):
            raise ValueError(
                "Invalid claimed entry price."
            )

        if not math.isclose(
            claimed,
            entry_price,
            rel_tol=0,
            abs_tol=1e-10,
        ):
            raise ValueError(
                "Claimed entry price does not match "
                "the historical entry candle."
            )

    return ValidatedHistoricalTrade(
        entry_price=entry_price,
        expiry_price=expiry_price,
        entry_time=entry_time,
        expiry_time=expiry_time,
        expiry_candle_time=(
            expiry_time - ONE_MINUTE
        ),
        candle_count=len(interval),
        provenance=provenance,
    )


def candles_available_at_signal_time(
    candles,
    signal_time,
):
    """
    Return only candles fully completed at signal_time.

    Useful for preventing look-ahead in signal calculations.
    """

    signal_time = require_utc(
        signal_time,
        "signal_time",
    )

    data = normalize_candles(candles)

    completed = data.loc[
        data["timestamp"] + pd.Timedelta(minutes=1)
        <= pd.Timestamp(signal_time)
    ]

    return completed.copy().reset_index(drop=True)

