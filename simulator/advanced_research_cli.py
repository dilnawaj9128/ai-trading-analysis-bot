
import argparse
from pathlib import Path

from simulator.advanced_research import (
    build_advanced_research,
    export_advanced_research,
)


def main():
    parser = argparse.ArgumentParser(
        description="Advanced historical research analytics"
    )

    parser.add_argument(
        "--datasets",
        nargs="+",
        required=True,
        help="Historical dataset directories",
    )

    parser.add_argument(
        "--output",
        default="reports/advanced_research.json",
    )

    args = parser.parse_args()

    report = build_advanced_research(
        args.datasets
    )

    analytics = report["advanced_analytics"]
    coverage = analytics["coverage"]

    print("\nADVANCED HISTORICAL RESEARCH")
    print("=" * 55)

    print(
        "Datasets requested:",
        report["datasets_requested"],
    )
    print(
        "Quality passed:",
        report["datasets_passed"],
    )
    print(
        "Quality failed:",
        report["datasets_failed"],
    )
    print(
        "Accepted:",
        report["datasets_accepted"],
    )
    print(
        "Duplicates:",
        report["datasets_duplicate"],
    )
    print(
        "Overlapping:",
        report["datasets_overlapping"],
    )
    print(
        "Unique candles:",
        report["total_valid_candles"],
    )

    print("\nDATA COVERAGE")
    print(
        "Observed minutes:",
        coverage["observed_minutes"],
    )
    print(
        "Expected minutes:",
        coverage["expected_minutes"],
    )
    print(
        "Missing minutes:",
        coverage["missing_minutes"],
    )
    print(
        "Coverage (%):",
        coverage["coverage_percent"],
    )

    print("\nHOURLY UTC ANALYSIS")

    for hour in analytics["hourly_utc"]:
        print(
            hour["hour_start_utc"],
            "candles=", hour["candle_count"],
            "average_range=", hour["average_range"],
        )

    print("\nVOLATILITY RANKING")

    for session in analytics["volatility_ranking"]:
        print(
            "Rank", session["volatility_rank"],
            "Session", session["session"],
            "Average range", session["average_range"],
        )

    output = export_advanced_research(
        report,
        Path(args.output),
    )

    print("\nJSON report:", output)
    print("Directional backtesting: BLOCKED")
    print("Execution: ANALYSIS ONLY")

    return 0 if report["datasets_failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())

