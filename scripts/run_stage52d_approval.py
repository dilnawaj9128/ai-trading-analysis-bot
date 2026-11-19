"""Stage 52D Part 4B offline approval CLI. No HTTP."""

import argparse
from pathlib import Path

from market_data.recovery_approval import (
    prepare_offline_approval,
    claim_offline_approval,
)
from market_data.recovery_preflight import evaluate_preflight


ROOT = Path("data/api_usage")
CASE = Path(
    "data/recovery_reports/"
    "stage52d_20261119_uncertain_case.json"
)
APPROVAL = Path(
    "data/recovery_reports/"
    "stage52d_new_request_approval.json"
)

ARCHIVE = Path(
    "data/recovery_reports/"
    "stage52d_historical_provider_credits.json"
)


def main():
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--approve-new-offline", action="store_true")
    group.add_argument("--claim-offline", action="store_true")
    args = parser.parse_args()

    if args.approve_new_offline:
        result = prepare_offline_approval(
            root=ROOT,
            case_path=CASE,
            archive_path=ARCHIVE,
            approval_path=APPROVAL,
            explicitly_approved=True,
        )
        print("Offline approval prepared:", result["approval_id"])

    elif args.claim_offline:
        result = claim_offline_approval(
            root=ROOT,
            case_path=CASE,
            archive_path=ARCHIVE,
            approval_path=APPROVAL,
        )
        print("Offline approval claimed:", result["approval_id"])

    else:
        result = evaluate_preflight(
            root=ROOT,
            case_path=CASE,
            archive_path=ARCHIVE,
        )
        print("=== STAGE 52D PART 4B STATUS ===")
        print("Preflight:", result["preflight"])
        print("Reasons:", result["reasons"])

    print("HTTP authorized: False")
    print("Network requests: 0")
    print("Old probe changed: False")


if __name__ == "__main__":
    main()
