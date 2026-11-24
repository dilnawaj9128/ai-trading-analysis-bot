"""Explicit one-shot normal EUR/USD research fetch with optional credit renewal.

May execute up to TWO separately accounted requests: first an opt-in new
credit-snapshot renewal IF stale, then the existing authorized fetch.
No automatic retries, background polling, or broker execution.
"""
import argparse
import os
from pathlib import Path

from config.market_config import create_research_config
from market_data.authorized_live_fetch import fetch_authorized_live_candles
from market_data.provider_credit_state import load_credit_state
from market_data.verified_credit_renewal import renew_verified_credits_once


def fetch_one_research_snapshot(*, approved=False, api_key=None, include_analysis=False, reconcile_verified=False):
    if approved is not True:
        raise ValueError("Explicit approval for up to 2 requests required")
    if not api_key:
        raise ValueError("Twelve Data API key missing")
    # Reconcile only independently VERIFIED recovery/renewal requests.
    # Existing UNCERTAIN, legacy, and receipt-less reservations stay held.
    if reconcile_verified is True:
        from market_data.verified_reservation_settlement import reconcile_verified_historical
        reconcile_verified_historical()
    refreshed = False
    if load_credit_state() is None:
        # A new explicitly approved request, NOT a retry of an old one.
        # An error must abort; do not run normal fetch on stale data.
        renew_verified_credits_once(approved=True, api_key=api_key)
        refreshed = True
        # Provider response is verified; remove only its request-bound local
        # duplicate reservation BEFORE seeking a separately authorized fetch.
        if reconcile_verified is True:
            reconcile_verified_historical()
    config = create_research_config("quotex", "forex", "EUR/USD", "1min", 15)
    result = fetch_authorized_live_candles(
        config, api_key=api_key, settle_verified=True,
    )
    outcome = {"status": "VERIFIED_NORMAL_FETCH", "candles": result["candles"],
               "credits_renewed": refreshed, "maximum_http_requests": 2,
               "analysis_only": True}
    if include_analysis:
        from market_data.live_analysis_bridge import analyze_fetched_candles
        outcome["analysis"] = analyze_fetched_candles(result)
    return outcome


def main():
    parser = argparse.ArgumentParser(description="One-shot real EUR/USD research fetch")
    parser.add_argument("--approve-up-to-two-requests", action="store_true",
                        help="Consent to up to 2 API requests / credits (renewal + normal fetch)")
    parser.add_argument("--analyze", action="store_true",
                        help="Analyze fetched candles in memory without any extra API request")
    args = parser.parse_args()
    if not args.approve_up_to_two_requests:
        print("PREVIEW ONLY: zero HTTP calls or budget reservations")
        print("Explicit flag can use up to two Twelve Data credits")
        return
    from dotenv import load_dotenv
    load_dotenv(dotenv_path=Path.cwd() / ".env")
    key = os.environ.get("TWELVE_DATA_API_KEY")
    if not key:
        raise SystemExit("BLOCKED: missing Twelve Data API key")
    try:
        outcome = fetch_one_research_snapshot(approved=True, api_key=key, include_analysis=args.analyze, reconcile_verified=True)
    except BaseException as exc:
        # Do not leak signed URLs or keys from requests exceptions.
        print("BLOCKED_OR_FAILED:", type(exc).__name__)
        print("No automatic retry. Preserve all audit files.")
        raise SystemExit(1)
    print("NORMAL_FETCH:", outcome["status"])
    print("CANDLES:", outcome["candles"])
    print("CREDIT_RENEWAL_USED:", outcome["credits_renewed"])
    print("ANALYSIS_ONLY: True")
    if args.analyze:
        import json
        print("RESEARCH_ANALYSIS:", json.dumps(outcome["analysis"], indent=2, default=str))


if __name__ == "__main__":
    main()
