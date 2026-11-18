
import argparse
import json
from pathlib import Path

from data.dataset_quality import audit_dataset
from data.quality_report_export import (
    export_quality_report,
)


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Read-only historical dataset quality audit "
            "with optional JSON report export"
        )
    )

    parser.add_argument(
        "--dataset",
        required=True,
        help="Directory containing CSV and acquisition receipt",
    )

    parser.add_argument(
        "--export",
        action="store_true",
        help="Export JSON quality report",
    )

    parser.add_argument(
        "--report-path",
        default=None,
        help="Optional custom JSON report path",
    )

    args = parser.parse_args()

    base = Path(args.dataset)

    csv_path = base / "eurusd_1min_utc.csv"
    receipt_path = base / "acquisition.json"

    report = audit_dataset(
        csv_path=csv_path,
        receipt_path=receipt_path,
    )

    print("\nHISTORICAL DATA QUALITY AUDIT")
    print("=" * 55)

    print("Status:", report["status"])
    print(
        "Structural integrity:",
        report["structural_integrity"],
    )
    print(
        "Directional backtesting: BLOCKED"
    )

    print("\nMETRICS")
    for key, value in report["metrics"].items():
        print(f"{key}: {value}")

    print("\nWARNINGS")
    for warning in report["warnings"]:
        print("-", warning)

    print("\nERRORS")
    for error in report["errors"]:
        print("-", error)

    if args.export or args.report_path:
        output_path = (
            Path(args.report_path)
            if args.report_path
            else base / "quality_report.json"
        )

        try:
            exported = export_quality_report(
                report=report,
                csv_path=csv_path,
                receipt_path=receipt_path,
                output_path=output_path,
            )

        except (
            OSError,
            ValueError,
            TypeError,
        ) as exc:
            print(
                "\nREPORT EXPORT FAILED:",
                exc,
            )
            return 1

        print("\nJSON report:", exported)

    return (
        0
        if report["structural_integrity"]
        else 1
    )


if __name__ == "__main__":
    raise SystemExit(main())

