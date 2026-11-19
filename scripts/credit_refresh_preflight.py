"""Read-only Twelve Data credit refresh preflight. No network calls."""
import os
from market_data.manual_credit_refresh import inspect_production_credit_refresh


def main():
    result = inspect_production_credit_refresh(
        api_key_present=bool(os.environ.get("TWELVE_DATA_API_KEY")),
    )
    print("=== CONTROLLED CREDIT REFRESH PREFLIGHT ===")
    print("Eligible for one explicitly approved request:",
          "YES" if result["ready_for_one_approved_request"] else "NO")
    for reason in result["reasons"]:
        print("-", reason)
    print("No HTTP request, budget reservation, or file change performed.")
    return 0 if result["ready_for_one_approved_request"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
