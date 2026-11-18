
"""Download and inspect Twelve Data historical EUR/USD."""

import argparse
from datetime import datetime, timezone
import sys

import pandas as pd

from data.twelve_data_historical import download_eurusd
from data.historical_sessions import export_sessions


def parse_time(value):
    result = datetime.fromisoformat(
        value.replace("Z", "+00:00")
    )

    if result.tzinfo is None:
        raise argparse.ArgumentTypeError(
            "Timestamp must include timezone."
        )

    return result.astimezone(timezone.utc)


def main(argv=None):
    parser = argparse.ArgumentParser(
        description=(
            "Download historical EUR/USD 1m candles. "
            "Research only."
        )
    )

    parser.add_argument(
        "--start", required=True, type=parse_time
    )
    parser.add_argument(
        "--end", required=True, type=parse_time
    )
    parser.add_argument(
        "--output", required=True
    )

    args = parser.parse_args(argv)

    try:
        csv_path, receipt_path = download_eurusd(
            start=args.start,
            end=args.end,
            output_dir=args.output,
        )

        candles = pd.read_csv(csv_path)

        session_paths, summaries = export_sessions(
            candles,
            f"{args.output}/sessions",
        )

        print("\nHISTORICAL DATA ACQUISITION")
        print("=" * 55)
        print("CSV:", csv_path)
        print("Receipt:", receipt_path)
        print("Sessions:", len(session_paths))

        for summary in summaries:
            print(
                f"Session {summary.session_id}: "
                f"{summary.candle_count} candles, "
                f"eligible={summary.eligible_for_comparison}"
            )

        print("\nFeed mode: UNKNOWN")
        print("Directional backtesting: BLOCKED")
        print("Broker verification: NONE")
        print("Execution: ANALYSIS ONLY")

        return 0

    except (
        ValueError,
        KeyError,
        OSError,
        FileExistsError,
    ) as error:
        print(
            f"ACQUISITION FAILED: {error}",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    sys.exit(main())

