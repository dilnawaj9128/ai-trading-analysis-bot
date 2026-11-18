
from __future__ import annotations

import hashlib
import json
from datetime import timedelta, timezone
from pathlib import Path

import pandas as pd


REQUIRED_COLUMNS = [
    "timestamp", "Open", "High", "Low", "Close"
]


def audit_dataset(
    csv_path: str | Path,
    receipt_path: str | Path,
) -> dict:
    """Read-only audit of historical OHLC data and receipt."""

    csv_path = Path(csv_path)
    receipt_path = Path(receipt_path)

    report = {
        "schema_version": 1,
        "status": "FAIL",
        "structural_integrity": False,
        "directional_backtesting_allowed": False,
        "errors": [],
        "warnings": [],
        "metrics": {},
    }

    errors = report["errors"]
    warnings = report["warnings"]
    metrics = report["metrics"]

    if not csv_path.is_file():
        errors.append("CSV file not found")
        return report

    if not receipt_path.is_file():
        errors.append("Acquisition receipt not found")
        return report

    try:
        receipt = json.loads(
            receipt_path.read_text(encoding="utf-8")
        )
        if not isinstance(receipt, dict):
            raise ValueError("Receipt must be an object")
    except (OSError, ValueError) as exc:
        errors.append(f"Invalid receipt: {exc}")
        return report

    actual_hash = hashlib.sha256(
        csv_path.read_bytes()
    ).hexdigest()

    expected_hash = receipt.get("csv_sha256")

    metrics["sha256_matches"] = (
        isinstance(expected_hash, str)
        and actual_hash == expected_hash
    )

    if not metrics["sha256_matches"]:
        errors.append("CSV SHA-256 mismatch")

    for field, expected in {
        "provider": "Twelve Data",
        "symbol": "EUR/USD",
        "timeframe": "1min",
        "requested_timezone": "UTC",
        "timestamp_semantics": "candle_open_utc",
    }.items():
        if receipt.get(field) != expected:
            errors.append(
                f"Unexpected receipt field: {field}"
            )

    if receipt.get("research_only") is not True:
        errors.append("Research-only flag missing")

    feed_mode = receipt.get("feed_mode", "unknown")
    metrics["feed_mode"] = feed_mode
    metrics["broker_verified"] = (
        receipt.get("broker_verified") is True
    )

    if (
        feed_mode == "unknown"
        or receipt.get("provider_feed_mode_verified") is not True
    ):
        warnings.append(
            "Provider feed mode is not independently verified"
        )

    if receipt.get("broker_verified") is not True:
        warnings.append(
            "Broker execution prices are not verified"
        )

    try:
        frame = pd.read_csv(csv_path)
    except (OSError, ValueError, pd.errors.ParserError) as exc:
        errors.append(f"Cannot read CSV: {exc}")
        return report

    if list(frame.columns) != REQUIRED_COLUMNS:
        errors.append("Unexpected CSV columns")
        return report

    metrics["candle_count"] = len(frame)

    if len(frame) == 0:
        errors.append("Dataset is empty")
        return report

    if (
        type(receipt.get("candle_count")) is not int
        or receipt["candle_count"] != len(frame)
    ):
        errors.append("Receipt candle count mismatch")

    try:
        # Require explicit timezone information in every row.
        raw_timestamps = frame["timestamp"].astype(str)

        if not raw_timestamps.str.contains(
            r"(?:Z|[+-]\d{2}:?\d{2})$",
            regex=True,
        ).all():
            raise ValueError(
                "Timezone-naive timestamp detected"
            )

        timestamps = pd.to_datetime(
            raw_timestamps,
            utc=True,
            errors="raise",
            format="ISO8601",
        )

        for column in REQUIRED_COLUMNS[1:]:
            frame[column] = pd.to_numeric(
                frame[column],
                errors="raise",
            )

    except (ValueError, TypeError) as exc:
        errors.append(f"Invalid candle values: {exc}")
        return report

    frame["timestamp"] = timestamps

    if frame[REQUIRED_COLUMNS].isna().any().any():
        errors.append("Missing candle values")

    duplicate_count = int(
        frame["timestamp"].duplicated().sum()
    )
    metrics["duplicate_count"] = duplicate_count

    if duplicate_count:
        errors.append("Duplicate timestamps detected")

    if not frame["timestamp"].is_monotonic_increasing:
        errors.append("Timestamps are not increasing")

    deltas = frame["timestamp"].diff().dropna()

    gap_count = int(
        (deltas > pd.Timedelta(minutes=1)).sum()
    )

    irregular_count = int(
        (deltas != pd.Timedelta(minutes=1)).sum()
    )

    metrics["gap_count"] = gap_count
    metrics["irregular_interval_count"] = irregular_count

    if irregular_count:
        errors.append("Non-contiguous 1-minute candles")

    if (
        frame["timestamp"].dt.second.ne(0).any()
        or frame["timestamp"].dt.microsecond.ne(0).any()
    ):
        errors.append("Candle timestamps not minute-aligned")

    price_columns = ["Open", "High", "Low", "Close"]

    import numpy as np

    values = frame[price_columns].to_numpy(dtype=float)

    if not np.isfinite(values).all():
        errors.append("Non-finite OHLC price detected")

    if (values <= 0).any():
        errors.append("Non-positive OHLC price detected")

    high = frame["High"]
    low = frame["Low"]
    opening = frame["Open"]
    closing = frame["Close"]

    invalid_ohlc = (
        (high < low)
        | (high < opening)
        | (high < closing)
        | (low > opening)
        | (low > closing)
    )

    metrics["invalid_ohlc_count"] = int(
        invalid_ohlc.sum()
    )

    if invalid_ohlc.any():
        errors.append("Invalid OHLC relationships")

    zero_range = high.eq(low)

    metrics["zero_range_count"] = int(
        zero_range.sum()
    )

    if zero_range.any():
        warnings.append(
            "Zero-range candles detected"
        )

    # Robust, descriptive outlier detection.
    # Flags are not automatic proof of bad market data.
    ranges = (high - low).to_numpy(dtype=float)

    if np.isfinite(ranges).all():
        median_range = float(np.median(ranges))
        mad = float(
            np.median(np.abs(ranges - median_range))
        )

        if mad > 0:
            outlier_count = int(
                (
                    ranges >
                    median_range + 10 * 1.4826 * mad
                ).sum()
            )
        else:
            outlier_count = 0
            if median_range > 0:
                outlier_count = int(
                    (ranges > median_range * 10).sum()
                )

        metrics["large_range_outlier_count"] = (
            outlier_count
        )

        if outlier_count:
            warnings.append(
                "Unusually large candle ranges detected"
            )

    # Self-reported flags do not prove feed authenticity.
    if receipt.get("provider_feed_mode_verified") is True:
        warnings.append(
            "Feed verification flag is self-reported; "
            "independent evidence is still required"
        )

    if receipt.get("broker_verified") is True:
        warnings.append(
            "Broker verification flag is self-reported; "
            "independent broker evidence is still required"
        )

    try:
        start = pd.Timestamp(
            receipt["requested_start"]
        )
        end = pd.Timestamp(
            receipt["requested_end"]
        )
        retrieved_at = pd.Timestamp(
            receipt["retrieved_at"]
        )

        if any(
            value.tzinfo is None
            for value in (start, end, retrieved_at)
        ):
            raise ValueError(
                "Receipt timestamps must be timezone-aware"
            )

        start = start.tz_convert("UTC")
        end = end.tz_convert("UTC")
        retrieved_at = retrieved_at.tz_convert("UTC")

        if start >= end:
            errors.append("Invalid requested time window")
        else:
            if not (
                (frame["timestamp"] >= start)
                & (frame["timestamp"] < end)
            ).all():
                errors.append(
                    "Candles outside requested window"
                )

            expected_count = int(
                (end - start) / timedelta(minutes=1)
            )

            metrics["expected_candle_count"] = (
                expected_count
            )

            if (
                (end - start) % timedelta(minutes=1)
                != timedelta(0)
            ):
                errors.append(
                    "Requested window not minute-aligned"
                )

            if (
                frame["timestamp"].iloc[0] != start
                or frame["timestamp"].iloc[-1]
                != end - timedelta(minutes=1)
                or len(frame) != expected_count
            ):
                errors.append(
                    "Dataset does not cover full requested window"
                )

        if (
            frame["timestamp"]
            + timedelta(minutes=1)
            > retrieved_at
        ).any():
            errors.append(
                "Incomplete candles at retrieval time"
            )

    except (KeyError, ValueError, TypeError) as exc:
        errors.append(
            f"Invalid receipt time metadata: {exc}"
        )

    metrics["first_timestamp"] = (
        frame["timestamp"].iloc[0].isoformat()
    )
    metrics["last_timestamp"] = (
        frame["timestamp"].iloc[-1].isoformat()
    )

    report["structural_integrity"] = not errors
    report["status"] = "PASS" if not errors else "FAIL"

    # Deliberately never grant directional backtesting
    # permissions based on a structural audit.
    report["directional_backtesting_allowed"] = False

    return report

