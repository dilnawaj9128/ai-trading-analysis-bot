"""Safe Stage 52D one-shot recovery entrypoint.

By default read-only preview. The explicit flag can consume one provider
credit ONLY on a configured local machine with TWELVE_DATA_API_KEY.
Never store a key in GitHub or CI secrets for this workflow.
"""
import argparse
from pathlib import Path
from market_data.recovery_transport import recover_once

ROOT = Path("data/api_usage")
REPORTS = Path("data/recovery_reports")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--approve-one-new-request",
        action="store_true",
        help="Explicitly authorize ONE new EUR/USD provider request; may use 1 credit",
    )
    args = parser.parse_args()

    if not args.approve_one_new_request:
        print("RECOVERY PREVIEW: no HTTP, no reservations, no state changes")
        print("Original fifth request remains UNCERTAIN.")
        return

    try:
        result = recover_once(
            approved=True,
            old_probe_path=ROOT / "approved_research_probe.json",
            case_path=REPORTS / "stage52d_20261119_uncertain_case.json",
            archive_path=REPORTS / "stage52d_historical_provider_credits.json",
            provider_path=ROOT / "provider_credits.json",
            budget_path=ROOT / "twelve_data_budget.json",
            claim_path=ROOT / "recovery_txn_claim.json",
            recovery_journal_path=ROOT / "stage52d_new_recovery_probe.json",
            csv_path=Path("data/real_market/stage52d_new_completed.csv"),
        )
    except BaseException as exc:
        # Never include exception message: request URLs can contain secrets.
        print("RECOVERY BLOCKED OR FAILED:", type(exc).__name__)
        print("No automatic retries; inspect audit journals offline.")
        raise SystemExit(1)
    for field in ("status", "candles", "credits_left", "csv_path", "old_request_outcome"):
        print(f"{field}: {result[field]}")
    print("RESEARCH ONLY. No broker orders. No claim of predictive accuracy.")


if __name__ == "__main__":
    main()
