"""Stage 32 offline CSV audit. Makes NO API requests and issues NO orders.

CSV alone is not evidence of live-provider provenance. It is intentionally
blocked from directional output; trusted provenance integration is a separate
review step.
"""
import argparse
from datetime import datetime, timezone
from pathlib import Path
import pandas as pd

from research.stage32_forward_safety import assess_snapshot, record_forward_snapshot


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--csv", default="data/real_market/latest_eurusd_completed.csv")
    p.add_argument("--journal", default="data/forward_testing/stage32_observations.jsonl")
    p.add_argument("--record", action="store_true")
    args = p.parse_args()
    observed = datetime.now(timezone.utc)
    # Do not infer 'live' or verified source from an arbitrary local CSV.
    try:
        candles = pd.read_csv(args.csv)
    except (OSError, pd.errors.ParserError) as exc:
        p.error(f"Could not read snapshot: {type(exc).__name__}")
    result = assess_snapshot(candles, observed_at=observed,
                             source_verified=False, feed_mode="unknown")
    print("STAGE 32 OFFLINE SNAPSHOT AUDIT")
    print("candles:", len(candles))
    print("observed_at_utc:", observed.isoformat())
    print("signal:", result["signal"])
    print("status:", result["status"])
    print("reason:", result["reason"])
    print("No API fetch / no order execution / no broker feed parity.")
    if args.record:
        saved = record_forward_snapshot(Path(args.journal), result,
                                        observed_at=observed)
        print("journal_recorded:", saved)


if __name__ == "__main__":
    main()
