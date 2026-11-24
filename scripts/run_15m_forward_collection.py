"""Safe 15-minute EUR/USD prospective collection controller.

Default: offline archive reconciliation and truthful progress summary, no API.
Optional --one-authorized-capture: exactly one bounded research attempt only
when no unresolved/uncertain renewal or usage-bootstrap request exists and
the existing provider credit guard is eligible. Never loops/retries or changes
strategy, reservations, source provenance or broker signals.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_JOURNAL = Path("data/research/prospective_accuracy")
DEFAULT_PROVIDER = Path("data/api_usage/provider_credits.json")
TARGET_NONPUSH = 100


def eligibility(*, provider=DEFAULT_PROVIDER, journal=DEFAULT_JOURNAL,
                now=None, target=TARGET_NONPUSH):
    from research.real_prediction_campaign import (
        prospective_scorecard, preflight_observation_window,
    )
    from market_data.provider_credit_state import load_credit_state
    from market_data.unified_request_guard import _load_ledger

    if type(target) is not int or target < 30:
        raise ValueError("Research target must be at least 30")
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("Timezone-aware now is required")
    journal, provider = Path(journal), Path(provider)
    score = prospective_scorecard(journal)
    counts = score["counts"]
    nonpush = counts["WIN"] + counts["LOSS"]
    result = {
        "status": "BLOCKED",
        "target_nonpush": target, "observed_nonpush": nonpush,
        "remaining_nonpush": max(0, target - nonpush),
        "abstained": counts["ABSTAINED"],
        "pending_observations": len([
            f for f in (journal / "observations").glob("*.json")
            if not (journal / "settlements" / f.name).is_file()
        ]),
        "reasons": [], "provider_requests": 0, "broker_orders": 0,
        "strategy_changed": False,
    }
    blockers = result["reasons"]
    if nonpush >= target:
        result["status"] = "SAMPLE_TARGET_REACHED_NO_NEW_FETCH"
        blockers.append("RESEARCH_SAMPLE_TARGET_ALREADY_REACHED")
    if score["invalid_evidence"]:
        blockers.append("INVALID_PROSPECTIVE_EVIDENCE_REQUIRES_REVIEW")
    try:
        window = preflight_observation_window(journal, now=now)
        if not window["eligible"]:
            blockers.append(window["reason"])
            result["next_eligible_utc"] = window.get("next_eligible_utc")
    except (OSError, ValueError, TypeError, KeyError):
        blockers.append("PROSPECTIVE_WINDOW_INVALID")
    try:
        ledger_path = provider.with_name(provider.name + ".reservations.json")
        if not ledger_path.is_file():
            blockers.append("RESERVATION_LEDGER_MISSING")
        else:
            ledger = _load_ledger(ledger_path)
            result["outstanding_reserved"] = ledger["reserved"]
            uncertain = sum(
                int(entry["status"] == "UNCERTAIN")
                for entry in ledger["requests"].values()
            )
            result["uncertain_requests"] = uncertain
            if uncertain:
                blockers.append("UNCERTAIN_PROVIDER_REQUESTS_REQUIRE_RECONCILIATION")
    except (OSError, ValueError, TypeError, KeyError):
        blockers.append("RESERVATION_LEDGER_INVALID")
    usage = provider.parent / "account_usage_bootstrap.json"
    renewal = provider.parent / "verified_credit_renewals.json"
    for path, label in (
        (usage, "ACCOUNT_USAGE_BOOTSTRAP"), (renewal, "CREDIT_RENEWAL"),
    ):
        try:
            if path.is_file():
                data = json.loads(path.read_text(encoding="utf-8"))
                attempts = data.get("attempts")
                if not isinstance(attempts, list):
                    raise ValueError("Invalid journal")
                if any(not isinstance(a, dict) or a.get("status") != "VERIFIED"
                       for a in attempts):
                    blockers.append(label + "_UNRESOLVED")
        except (OSError, ValueError, TypeError, KeyError):
            blockers.append(label + "_JOURNAL_INVALID")
    # A fresh snapshot is necessary but never sufficient to approve a request.
    try:
        fresh = load_credit_state(path=provider, now=now)
        result["fresh_credit_snapshot_available"] = fresh is not None
        if fresh is None:
            blockers.append("CREDIT_SNAPSHOT_STALE_OR_MISSING")
    except (OSError, ValueError, TypeError, KeyError):
        blockers.append("CREDIT_SNAPSHOT_INVALID")
    if not blockers:
        result["status"] = "PRECHECK_ONLY_EXISTING_REQUEST_GUARD_STILL_REQUIRED"
    return result


def offline_progress(*, journal=DEFAULT_JOURNAL, provider=DEFAULT_PROVIDER,
                     settle_archives=True):
    from scripts.run_accuracy_all import archive_settlement_pass
    archived = (
        archive_settlement_pass(journal)
        if settle_archives else {"status": "SKIPPED"}
    )
    readiness = eligibility(provider=provider, journal=journal)
    return {"archived_settlements": archived, "readiness": readiness,
            "new_provider_requests": 0, "broker_orders": 0,
            "accuracy_verified": False}


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--journal", type=Path, default=DEFAULT_JOURNAL)
    p.add_argument("--provider", type=Path, default=DEFAULT_PROVIDER)
    p.add_argument("--one-authorized-capture", action="store_true",
                   help="One opt-in guarded attempt, only after all offline prerequisites pass")
    p.add_argument("--preview-only", action="store_true",
                   help="No observation/settlement files changed; no provider HTTP")
    args = p.parse_args(argv)
    report = offline_progress(journal=args.journal, provider=args.provider,
                              settle_archives=not args.preview_only)
    readiness = report["readiness"]
    live = {"status": "NOT_REQUESTED", "provider_requests": 0}
    if args.one_authorized_capture:
        if readiness["status"] != "PRECHECK_ONLY_EXISTING_REQUEST_GUARD_STILL_REQUIRED":
            live = {"status": "BLOCKED_NO_HTTP",
                    "reasons": readiness["reasons"], "provider_requests": 0}
        else:
            from dotenv import load_dotenv
            import os
            load_dotenv(dotenv_path=Path.cwd() / ".env")
            key = os.environ.get("TWELVE_DATA_API_KEY")
            if not key:
                live = {"status": "BLOCKED_MISSING_API_KEY", "provider_requests": 0}
            else:
                from scripts.run_real_prediction_live_once import capture_live_once
                try:
                    live = capture_live_once(api_key=key, approved=True,
                                             root=args.journal)
                except Exception as exc:
                    live = {"status": "BLOCKED_OR_FAILED",
                            "exception_type": type(exc).__name__,
                            "possible_new_reservation": True,
                            "no_automatic_retry": True}
    report["live"] = live
    report["readiness_after"] = eligibility(
        provider=args.provider, journal=args.journal
    )
    print(json.dumps(report, indent=2, sort_keys=True, default=str))
    print("NO BROKER ORDERS / NO STRATEGY TUNING / NO SYNTHETIC OUTCOMES")
    return 2 if live["status"] in ("BLOCKED_OR_FAILED", "BLOCKED_MISSING_API_KEY") else 0


if __name__ == "__main__":
    raise SystemExit(main())
