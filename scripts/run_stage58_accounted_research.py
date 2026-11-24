"""Safe one-shot Stage 58 EUR/USD research run.

Preview by default (zero HTTP). --approve-up-to-two-requests permits
one account usage bootstrap if needed and one normally authorized candle
fetch. Each request has its own durable quota reservation. Never retries,
places orders, or promotes unverified broker data to trade signals.
"""
import argparse
import json
import os
from pathlib import Path

from config.market_config import create_research_config
from market_data.account_usage_bootstrap import bootstrap_account_usage_once
from market_data.authorized_live_fetch import fetch_authorized_live_candles
from market_data.provider_credit_state import load_credit_state
from market_data.verified_reservation_settlement import reconcile_verified_historical


def run_once(*, approved=False, api_key=None, analyze=False, save_csv=False, verify_feed=False):
    if approved is not True:
        raise ValueError("Explicit approval for up to two requests required")
    if not api_key:
        raise ValueError("API key missing")

    # Never settle unverified history, only independently attested responses.
    reconciliation = reconcile_verified_historical()

    refreshed = False
    if load_credit_state() is None:
        # One separately authorized NEW usage request. Its result provides
        # fresh provider evidence without falsely settling any old timeout.
        bootstrap_account_usage_once(approved=True, api_key=api_key)
        refreshed = True
    if load_credit_state() is None:
        raise ValueError("Provider account usage did not refresh credits")

    config = create_research_config("quotex", "forex", "EUR/USD", "1min", 15)
    candles = fetch_authorized_live_candles(
        config, api_key=api_key, settle_verified=True
    )
    report = {
        "status": "VERIFIED_RESEARCH_FETCH",
        "candles": candles["candles"],
        "gaps": candles["gaps"],
        "stale": candles["stale"],
        "latest_utc": candles["latest_utc"],
        "credits_refreshed": refreshed,
        "maximum_http_requests": 2,
        "historical_reserved_remaining": reconciliation["outstanding_reserved"],
        "analysis_only": True,
        "trading_enabled": False,
    }
    if verify_feed:
        from market_data.regular_forex_feed_evidence import classify_authorized_fetch
        report["feed_mode_evidence"] = classify_authorized_fetch(candles)
    if save_csv:
        from market_data.research_capture import save_verified_research_frame
        report["capture"] = save_verified_research_frame(candles)
    if analyze:
        from market_data.live_analysis_bridge import analyze_fetched_candles
        report["analysis"] = analyze_fetched_candles(candles)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--approve-up-to-two-requests", action="store_true",
                        help="Consent to one usage check and one candle fetch (up to 2 credits)")
    parser.add_argument("--analyze", action="store_true",
                        help="Analyze fetched candles without an additional API request")
    parser.add_argument("--save-csv", action="store_true",
                        help="Persist the SAME fetched candles to immutable research CSV; no additional HTTP")
    parser.add_argument("--verify-feed", action="store_true",
                        help="Classify existing fetched data using official Twelve Data feed documentation; no extra HTTP")
    args = parser.parse_args()
    if not args.approve_up_to_two_requests:
        print("PREVIEW: zero HTTP requests, zero writes, zero trades")
        print("With approval: up to two separately accounted provider requests.")
        return
    from dotenv import load_dotenv
    load_dotenv(dotenv_path=Path.cwd() / ".env")
    try:
        result = run_once(
            approved=True, api_key=os.environ.get("TWELVE_DATA_API_KEY"),
            analyze=args.analyze, save_csv=args.save_csv, verify_feed=args.verify_feed,
        )
    except BaseException as exc:
        # Never print provider request exception bodies that could expose URLs.
        print("BLOCKED_OR_FAILED:", type(exc).__name__)
        print("No automatic retry. Preserve all local accounting journals.")
        raise SystemExit(1)
    print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()
