import argparse
from pathlib import Path

from simulator.session_research import (
    analyze_multiple_sessions,
    export_research_report,
)


def main():
    parser = argparse.ArgumentParser(
        description="Safe multi-session historical research"
    )

    parser.add_argument(
        "--datasets",
        nargs="+",
        required=True,
        help="Historical dataset directories",
    )

    parser.add_argument(
        "--output",
        default="reports/research_report.json",
    )

    args = parser.parse_args()

    report = analyze_multiple_sessions(
        args.datasets
    )

    print("\nMULTI-SESSION HISTORICAL RESEARCH")
    print("=" * 55)

    for key, label in [
        ("datasets_requested", "Datasets requested"),
        ("datasets_passed", "Quality passed"),
        ("datasets_failed", "Quality failed"),
        ("datasets_accepted", "Accepted"),
        ("datasets_duplicate", "Duplicates"),
        ("datasets_overlapping", "Overlapping"),
        ("total_valid_candles", "Unique accepted candles"),
    ]:
        print(f"{label}: {report[key]}")

    for index, session in enumerate(
        report["sessions"], start=1
    ):
        print(f"\nSESSION {index}")
        print("Dataset:", session["dataset"])
        print("Quality:", session["status"])
        print("Selection:", session["selection_status"])

        if session["selection_reason"]:
            print("Reason:", session["selection_reason"])

        stats = session["statistics"]

        if stats is not None:
            print("Candles:", stats["candle_count"])
            print(
                "Net change (%):",
                round(stats["net_change_percent"], 6),
            )
            print(
                "Bullish / Bearish / Doji:",
                stats["bullish_candles"],
                stats["bearish_candles"],
                stats["doji_candles"],
            )

    combined = report["combined_statistics"]

    print("\nCOMBINED ACCEPTED DATA")
    print("Candles:", combined["candle_count"])
    print(
        "Bullish / Bearish / Doji:",
        combined["bullish_candles"],
        combined["bearish_candles"],
        combined["doji_candles"],
    )
    print("Average range:", combined["average_range"])

    output = export_research_report(
        report, Path(args.output)
    )

    print("\nJSON report:", output)
    print("Directional backtesting: BLOCKED")
    print("Execution: ANALYSIS ONLY")

    return 0 if report["datasets_failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
