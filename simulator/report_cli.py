
"""
Stage 6.4 reporting CLI.

Usage:
    python3 -m simulator.report_cli
    python3 -m simulator.report_cli --source MANUAL_TEST
    python3 -m simulator.report_cli --source HISTORICAL_RESEARCH
    python3 -m simulator.report_cli --expiry 5
    python3 -m simulator.report_cli --history
"""

import argparse

from database.repository import PaperTradingRepository
from simulator.performance_analytics import (
    build_performance_reports,
    calculate_report,
    filter_trades,
    print_report,
    print_trade_history,
)


def main():
    parser = argparse.ArgumentParser(
        description="Read-only paper trading performance analytics."
    )

    parser.add_argument(
        "--db",
        default="data/paper_trading.db",
        help="SQLite database path.",
    )

    parser.add_argument(
        "--source",
        choices=["MANUAL_TEST", "HISTORICAL_RESEARCH"],
        default=None,
    )

    parser.add_argument(
        "--expiry",
        type=int,
        choices=[1, 5, 15],
        default=None,
    )

    parser.add_argument(
        "--result",
        choices=["WIN", "LOSS", "PUSH", "OPEN"],
        default=None,
    )

    parser.add_argument(
        "--history",
        action="store_true",
        help="Display filtered trade history.",
    )

    args = parser.parse_args()

    # Repository initialization is not strictly read-only:
    # it can create or migrate tables. Stage 6.4 CLI therefore
    # first verifies that the existing database file is present.
    from pathlib import Path

    if not Path(args.db).is_file():
        parser.error(
            f"Database does not exist: {args.db}"
        )

    repository = PaperTradingRepository(args.db)
    trades = repository.get_all_trades()

    if args.history:
        selected = filter_trades(
            trades,
            source=args.source,
            result=args.result,
            expiry_minutes=args.expiry,
        )

        print_trade_history(selected)
        return

    if (
        args.source is not None
        or args.expiry is not None
        or args.result is not None
    ):
        selected = filter_trades(
            trades,
            source=args.source,
            result=args.result,
            expiry_minutes=args.expiry,
        )

        print_report(
            "FILTERED PAPER TRADING PERFORMANCE",
            calculate_report(selected),
        )
        return

    reports = build_performance_reports(trades)

    print()
    print("STAGE 6.4 - PAPER TRADING ANALYTICS")
    print("Research / simulation only; not broker verified.")

    print_report(
        "OVERALL PERFORMANCE",
        reports["overall"],
    )

    print_report(
        "MANUAL TEST PERFORMANCE",
        reports["sources"]["MANUAL_TEST"],
    )

    print_report(
        "HISTORICAL RESEARCH PERFORMANCE",
        reports["sources"]["HISTORICAL_RESEARCH"],
    )

    for expiry in (1, 5, 15):
        print_report(
            f"{expiry}-MINUTE EXPIRY PERFORMANCE",
            reports["expiry"][expiry],
        )


if __name__ == "__main__":
    main()

