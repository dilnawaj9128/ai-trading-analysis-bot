"""Single-command, evidence-only recovery of CURRENT EUR/USD research quota readiness.

It NEVER overwrites the 19 historical unresolved requests or claims their
outcomes are known. The opt-in mode makes at most ONE NEW, separately
journaled /api_usage request, which can consume one provider credit.
NO retries, NO automated trading, NO candle requests.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from market_data.provider_credit_state import DEFAULT_PATH
from market_data.independent_usage_recovery import (
    recover_once, verified_independent_recovery,
)
from scripts.run_15m_forward_collection import eligibility
from scripts.run_reservation_evidence_audit import audit as reservation_audit
from market_data.verified_reservation_settlement import reconcile_verified_historical


def run(*, approved=False, api_key=None, provider=DEFAULT_PATH,
        journal=Path("data/research/prospective_accuracy")):
    provider = Path(provider)
    try:
        old = reconcile_verified_historical(provider_path=provider)
    except (OSError, ValueError, TypeError, KeyError, RuntimeError) as exc:
        old = {"status": "RECONCILIATION_BLOCKED",
               "exception_type": type(exc).__name__}
    pre = eligibility(provider=provider, journal=journal)
    before = reservation_audit(provider)
    outcome = {"status": "NO_NEW_REQUEST", "new_http_requests": 0}
    if approved:
        if pre.get("independent_current_usage_verified"):
            outcome = {"status": "ALREADY_INDEPENDENTLY_VERIFIED", "new_http_requests": 0}
        elif not api_key:
            outcome = {"status": "BLOCKED_NO_API_KEY", "new_http_requests": 0}
        else:
            try:
                outcome = recover_once(approved=True, api_key=api_key,
                                       provider_path=provider)
            except Exception as exc:
                # Request exception text may contain credentials. Never print.
                outcome = {
                    "status": "BLOCKED_OR_UNCERTAIN",
                    "exception_type": type(exc).__name__,
                    "new_http_requests": "0_OR_1_CHECK_JOURNAL",
                    "do_not_retry": True,
                }
    post = eligibility(provider=provider, journal=journal)
    after = reservation_audit(provider)
    return {
        "status": (
            "FRESH_OPERATIONAL_USAGE_VERIFIED_HISTORICAL_UNRESOLVED"
            if post.get("independent_current_usage_verified")
            else "SAFE_BLOCKERS_REMAIN"
        ),
        "before": {
            "readiness": pre,
            "reservations": before["outstanding_reserved"],
        },
        "new_usage_verification": outcome,
        "after": {
            "readiness": post,
            "reservations": after["outstanding_reserved"],
        },
        "verified_old_reconciliation": old.get("status"),
        "old_pending_or_uncertain_not_manually_cleared": True,
        "new_forward_observations": 0,
        "broker_orders": 0,
    }


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--approve-one-usage-request", action="store_true",
                   help="One NEW accounted usage request, max 1 provider credit")
    args = p.parse_args(argv)
    key = None
    if args.approve_one_usage_request:
        from dotenv import load_dotenv
        import os
        load_dotenv(dotenv_path=Path.cwd() / ".env")
        key = os.environ.get("TWELVE_DATA_API_KEY")
    report = run(approved=args.approve_one_usage_request, api_key=key)
    print(json.dumps(report, indent=2, sort_keys=True, default=str))
    print("NO TRADES / NO REPLAY / NO HISTORICAL LEDGER RESET")
    return 0 if report["status"].startswith("FRESH_OPERATIONAL") else 2


if __name__ == "__main__":
    raise SystemExit(main())
