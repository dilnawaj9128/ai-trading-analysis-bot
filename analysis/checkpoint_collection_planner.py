"""Read-only checkpoint-aware historical collection planning."""

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from market_data.resumable_collector import validate_batch
from market_data.session_batch_planner import plan_session_batches


@dataclass(frozen=True)
class CheckpointPlan:
    total_batches: int
    cached_batches: int
    pending_batches: int
    requests_this_run: int
    invalid_checkpoints: int
    job_dir: Path


def create_checkpoint_plan(
    *,
    symbol,
    start,
    end,
    output_dir,
    interval="1min",
    batch_candles=400,
    max_requests=5,
):
    if type(batch_candles) is not int or not 2 <= batch_candles <= 4999:
        raise ValueError("Invalid batch_candles")

    if type(max_requests) is not int or max_requests < 1:
        raise ValueError("Invalid max_requests")

    start = pd.Timestamp(start)
    end = pd.Timestamp(end)

    if start.tzinfo is None or end.tzinfo is None or start >= end:
        raise ValueError("Invalid UTC window")

    start = start.tz_convert("UTC")
    end = end.tz_convert("UTC")

    batches = plan_session_batches(
        start=start,
        end=end,
        interval=interval,
        batch_candles=batch_candles,
    )

    manifest = {
        "symbol": symbol,
        "timeframe": interval,
        "start": start.isoformat(),
        "end": end.isoformat(),
        "batch_candles": batch_candles,
        "planner_version": "forex-session-v1",
    }

    fingerprint = hashlib.sha256(
        json.dumps(manifest, sort_keys=True).encode()
    ).hexdigest()[:16]

    job_dir = Path(output_dir) / fingerprint

    cached = 0
    invalid = 0

    for index, (batch_start, batch_end) in enumerate(batches):
        path = job_dir / f"batch_{index:05d}.csv"

        if not path.exists():
            continue

        try:
            validate_batch(
                pd.read_csv(path),
                batch_start,
                batch_end,
                interval,
                require_complete=True,
            )
            cached += 1
        except (ValueError, KeyError, pd.errors.ParserError, OSError):
            invalid += 1
        except Exception:
            invalid += 1

    pending = len(batches) - cached

    return CheckpointPlan(
        total_batches=len(batches),
        cached_batches=cached,
        pending_batches=pending,
        requests_this_run=min(pending, max_requests),
        invalid_checkpoints=invalid,
        job_dir=job_dir,
    )
