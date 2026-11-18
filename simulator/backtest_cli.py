
"""Stage 6.6.3 - Historical backtesting CLI.

No real trading. No SQLite writes.
"""

import argparse
import sys
from pathlib import Path

from simulator.dataset_trust import verify_dataset
from simulator.expiry_comparison import (
    compare_expiries,
    print_expiry_comparison,
)
from simulator.backtest_export import (
    export_backtest_reports,
)


def build_parser():
    parser = argparse.ArgumentParser(
        description=(
            "Historical EUR/USD research backtesting. "
            "Analysis only; no broker orders."
        )
    )

    parser.add_argument(
        "--csv",
        required=True,
        help="Historical 1-minute OHLC CSV path.",
    )

    parser.add_argument(
        "--manifest",
        required=True,
        help="Dataset provenance manifest JSON.",
    )

    parser.add_argument(
        "--trust-registry",
        required=True,
        help="Independently maintained trusted registry.",
    )

    parser.add_argument(
        "--expiry",
        choices=("1", "5", "15", "all"),
        default="all",
        help="Expiry report to display; all are evaluated.",
    )

    parser.add_argument(
        "--stake",
        type=float,
        default=50.0,
    )

    parser.add_argument(
        "--payout",
        type=float,
        default=0.80,
    )

    parser.add_argument(
        "--output",
        default="reports/backtests/latest",
        help="Output directory for JSON and CSV files.",
    )

    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)

    try:
        verified = verify_dataset(
            args.csv,
            args.manifest,
            args.trust_registry,
        )

        comparison = compare_expiries(
            args.csv,
            verified.provenance,
            stake=args.stake,
            payout_rate=args.payout,
        )

        if args.expiry == "all":
            print_expiry_comparison(comparison)
        else:
            expiry = int(args.expiry)
            report = comparison.reports[expiry]

            print("\nHISTORICAL RESEARCH REPORT")
            print("=" * 45)
            print("Expiry:", expiry, "minutes")
            print("Signals:", report.signals_checked)
            print("NO TRADE:", report.no_trade_count)
            print("Trades:", len(report.trades))
            print("Wins:", report.wins)
            print("Losses:", report.losses)
            print("Pushes:", report.pushes)
            print("Win rate:", report.win_rate)
            print("Total P&L:", report.total_pnl)
            print("Max drawdown:", report.max_drawdown)
            print("=" * 45)

        paths = export_backtest_reports(
            comparison,
            verified,
            args.output,
        )

        print("\nREPORT FILES")
        for name, path in paths.items():
            print(f"{name}: {path}")

        print("\nExecution mode: ANALYSIS ONLY")
        print("SQLite paper account: NOT MODIFIED")

        return 0

    except (
        ValueError,
        FileNotFoundError,
        OSError,
        TypeError,
    ) as error:
        print(
            f"BACKTEST BLOCKED: {error}",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    sys.exit(main())

