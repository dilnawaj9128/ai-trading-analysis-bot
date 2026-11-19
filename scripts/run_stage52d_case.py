"""Offline recovery case generation. No network requests."""

import argparse
from pathlib import Path

from market_data.recovery_case import (
    build_case,
    save_case_exclusive,
)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--record", action="store_true",
        help="Write a separate, immutable-by-interface recovery case",
    )
    args = parser.parse_args()

    root = Path("data/api_usage")
    case = build_case(root)

    print("=== STAGE 52D PART 3 ===")
    print("Classification:", case["classification"])
    print("Probe:", case["probe_started_at"])
    print(
        "Provider evidence:",
        case["provider_observation"]["source"],
    )
    print(
        "Request-specific match:",
        case["provider_observation"]["request_specific_match"],
    )
    print(
        "New API request authorized:",
        case["decision"]["new_api_request_authorized"],
    )

    if args.record:
        destination = Path(
            "data/recovery_reports/"
            "stage52d_20261119_uncertain_case.json"
        )
        save_case_exclusive(case, destination)
        print("Case saved:", destination)
    else:
        print("Preview only. No report saved.")

    print("Network requests: 0")
    print("Original journals modified: 0")


if __name__ == "__main__":
    main()
