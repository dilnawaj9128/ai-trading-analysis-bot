"""Opt-in credit freshness renewal. Use `python -m scripts.run_verified_credit_renewal`."""
import argparse
import os
from pathlib import Path

from market_data.verified_credit_renewal import renew_verified_credits_once


def main():
    parser = argparse.ArgumentParser(description="Research-only Twelve Data credit renewal")
    parser.add_argument("--approve-one-new-request", action="store_true",
                        help="Make ONE new, accounted EUR/USD API request (may cost 1 credit)")
    args = parser.parse_args()
    if not args.approve_one_new_request:
        print("PREVIEW ONLY: zero HTTP requests or reservations")
        print("Historical UNCERTAIN requests remain unchanged")
        return
    from dotenv import load_dotenv
    load_dotenv(dotenv_path=Path.cwd() / ".env")
    if not os.environ.get("TWELVE_DATA_API_KEY"):
        raise SystemExit("BLOCKED: TWELVE_DATA_API_KEY missing")
    try:
        result = renew_verified_credits_once(approved=True)
    except BaseException as exc:
        # Never print exception bodies: some HTTP errors include secret URLs.
        print("BLOCKED_OR_FAILED:", type(exc).__name__)
        print("NO RETRIES. Inspect provider audit files offline.")
        raise SystemExit(1)
    print("RENEWAL:", result["status"])
    print("CANDLES:", result["candles"])
    print("PROVIDER_CREDITS_LEFT:", result["credits_left"])
    print("One provider request used. No trade execution. Old history preserved.")


if __name__ == "__main__":
    main()
