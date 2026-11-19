"""Stage 45: offline candle quality and split-boundary audit.

Read-only; no API calls, trade execution, or source promotion.
All timestamps are interpreted as candle CLOSE times.
"""

import argparse
import csv
import json
import math
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

from scripts.run_stage41_evidence_audit import (
    sha256_file,
    write_evidence_report,
)

DEFAULT_CSV = Path("data/historical/eurusd_1min_1day.csv")
DEFAULT_OUT = Path("data/research/stage45")
ONE_MINUTE = timedelta(minutes=1)
EXPIRY = timedelta(minutes=15)


def parse_timestamp(value):
    if not isinstance(value, str):
        raise ValueError("Timestamp missing")

    stamp = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    if stamp.tzinfo is None:
        raise ValueError("Naive timestamp")

    return stamp.astimezone(timezone.utc)


def parse_candles(path):
    """Parse OHLC rows without silently sorting or dropping bad data."""
    path = Path(path)
    rows = []

    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames:
            raise ValueError("CSV header missing")

        columns = {name.strip().lower(): name
                   for name in reader.fieldnames}

        required = ("timestamp", "open", "high", "low", "close")
        if any(name not in columns for name in required):
            raise ValueError("Required OHLC columns missing")

        for line, row in enumerate(reader, start=2):
            try:
                stamp = parse_timestamp(row[columns["timestamp"]])
                prices = {
                    name: float(row[columns[name]])
                    for name in ("open", "high", "low", "close")
                }
            except (ValueError, TypeError, KeyError, OverflowError) as exc:
                raise ValueError(f"Invalid row at line {line}") from exc

            if any(not math.isfinite(value) or value <= 0
                   for value in prices.values()):
                raise ValueError(f"Nonpositive/nonfinite OHLC at line {line}")

            if (
                prices["high"] < max(
                    prices["open"], prices["close"], prices["low"]
                )
                or prices["low"] > min(
                    prices["open"], prices["close"], prices["high"]
                )
            ):
                raise ValueError(f"Inconsistent OHLC at line {line}")

            rows.append({"timestamp": stamp, **prices})

    if not rows:
        raise ValueError("Dataset empty")

    return rows


def quality(rows):
    timestamps = [r["timestamp"] for r in rows]
    duplicate_count = sum(
        count - 1 for count in Counter(timestamps).values()
        if count > 1
    )

    backward_count = sum(
        left > right
        for left, right in zip(timestamps, timestamps[1:])
    )

    # Count missing minute slots only across strictly forward jumps.
    missing_minutes = 0
    irregular_spacing = 0

    for left, right in zip(timestamps, timestamps[1:]):
        delta = (right - left).total_seconds()

        if delta > 60:
            if delta % 60 == 0:
                missing_minutes += int(delta // 60) - 1
            else:
                irregular_spacing += 1
        elif 0 < delta < 60:
            irregular_spacing += 1

    aligned = sum(
        ts.second == 0 and ts.microsecond == 0
        for ts in timestamps
    )

    passed = (
        duplicate_count == 0
        and backward_count == 0
        and missing_minutes == 0
        and irregular_spacing == 0
        and aligned == len(rows)
    )

    return {
        "rows": len(rows),
        "duplicate_timestamps": duplicate_count,
        "backward_timestamp_pairs": backward_count,
        "missing_minute_slots": missing_minutes,
        "irregular_spacing_pairs": irregular_spacing,
        "minute_aligned_rows": aligned,
        "first_close_utc": min(timestamps).isoformat(),
        "last_close_utc": max(timestamps).isoformat(),
        "continuous_one_minute_candles": passed,
    }


def split_safety(rows, training_fraction=0.8, expiry_minutes=15):
    """Assess safe settlement assignment at chronological split.

    Entry is at a candle close; settlement is exactly 15 later.
    Training settlements cannot consume holdout candle prices.
    """
    if not 0 < training_fraction < 1:
        raise ValueError("Invalid training fraction")
    if expiry_minutes != 15:
        raise ValueError("Stage 45 audits 15-minute expiry only")

    if len(rows) < 32:
        return {
            "status": "INSUFFICIENT_DATA",
            "training_rows": 0,
            "holdout_rows": 0,
            "safe_training_entries": 0,
            "safe_holdout_entries": 0,
        }

    cut = int(len(rows) * training_fraction)

    timestamps = [r["timestamp"] for r in rows]
    training_end = timestamps[cut - 1]
    holdout_end = timestamps[-1]
    candle_times = set(timestamps)

    train_entries = timestamps[:cut]
    holdout_entries = timestamps[cut:]

    safe_training = sum(
        entry + EXPIRY <= training_end
        and entry + EXPIRY in candle_times
        for entry in train_entries
    )
    safe_holdout = sum(
        entry + EXPIRY <= holdout_end
        and entry + EXPIRY in candle_times
        for entry in holdout_entries
    )

    unsafe_boundary = sum(
        entry + EXPIRY > training_end
        for entry in train_entries
    )

    return {
        "status": "ASSESSED",
        "training_rows": cut,
        "holdout_rows": len(rows) - cut,
        "training_last_close_utc": training_end.isoformat(),
        "holdout_first_close_utc": timestamps[cut].isoformat(),
        "safe_training_entries": safe_training,
        "safe_holdout_entries": safe_holdout,
        "training_entries_excluded_at_boundary": unsafe_boundary,
        "expiry_minutes": expiry_minutes,
        "holdout_used_for_training_settlements": False,
        "note": (
            "Entry/settlement availability only; does not inspect "
            "indicator warmup, overlapping trades or strategy logic."
        ),
    }


def audit(csv_path=DEFAULT_CSV):
    rows = parse_candles(csv_path)
    checks = quality(rows)
    split = split_safety(rows)

    return {
        "stage": 45,
        "dataset_path": str(Path(csv_path)),
        "dataset_sha256": sha256_file(csv_path),
        "dataset_origin_verified": False,
        "feed_mode": "UNKNOWN",
        "data_quality": checks,
        "chronological_split": split,
        "research_status": (
            "RESEARCH_ONLY"
            if checks["continuous_one_minute_candles"]
            else "BLOCKED_DATA_QUALITY"
        ),
        "forward_accuracy_proven": False,
        "api_requests_executed": 0,
        "analysis_only": True,
        "execution_enabled": False,
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument(
        "action", nargs="?", choices=("audit", "export"),
        default="audit"
    )
    p.add_argument("--csv", type=Path, default=DEFAULT_CSV)
    p.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = p.parse_args()

    try:
        result = audit(args.csv)

        print("=== STAGE 45 DATASET QUALITY AUDIT ===")
        print(json.dumps(result, indent=2))

        if args.action == "export":
            path, created = write_evidence_report(
                result, args.out
            )
            print("report_path:", path)
            print("new_report_created:", created)

    except (OSError, ValueError, KeyError, TypeError) as exc:
        p.exit(1, f"BLOCKED: {type(exc).__name__}: {exc}\n")

    print("API requests: 0")
    print("Live signals: NOT AUTHORIZED")
    print("Trading execution: DISABLED")


if __name__ == "__main__":
    main()
