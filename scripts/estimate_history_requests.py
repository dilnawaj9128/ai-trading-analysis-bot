import argparse

import pandas as pd

from market_data.session_batch_planner import plan_session_batches


def main():
    parser = argparse.ArgumentParser(
        description="Estimate forex historical API requests without downloading"
    )

    parser.add_argument("--days", type=int, default=30)
    parser.add_argument("--batch-candles", type=int, default=400)
    parser.add_argument("--interval", default="1min")

    args = parser.parse_args()

    if args.days < 1:
        parser.error("--days must be at least 1")

    end = pd.Timestamp.now(tz="UTC").floor("min")
    start = end - pd.Timedelta(days=args.days)

    batches = plan_session_batches(
        start=start,
        end=end,
        interval=args.interval,
        batch_candles=args.batch_candles,
    )

    candle_seconds = {
        "1min": 60,
        "5min": 300,
        "15min": 900,
    }

    if args.interval not in candle_seconds:
        parser.error("Unsupported interval")

    step = candle_seconds[args.interval]

    candles = sum(
        int((batch_end - batch_start).total_seconds() / step)
        for batch_start, batch_end in batches
    )

    print("\n=== HISTORICAL COLLECTION DRY RUN ===")
    print(f"Start UTC:         {start}")
    print(f"End UTC:           {end}")
    print(f"Timeframe:         {args.interval}")
    print(f"Batch candles:     {args.batch_candles}")
    print(f"Expected candles:  {candles}")
    print(f"Planned requests:  {len(batches)}")
    print("Actual API calls:  0")
    print("Execution enabled: False")
    print("=====================================\n")


if __name__ == "__main__":
    main()
