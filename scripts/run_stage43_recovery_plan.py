"""Stage 43: controlled provider recovery planning.

Read-only provider assessment. No API calls, no credit reservations,
no journal changes, no broker execution. Export is optional and
creates an immutable, content-addressed JSON planning report.
"""

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from scripts.run_stage42_readiness import (
    readiness,
    PROBE,
    BUDGET,
    CREDITS,
    CSV,
)
from scripts.run_stage41_evidence_audit import (
    write_evidence_report,
)

OUT = Path("data/recovery/stage43")


def build_plan(readiness_report):
    """Separate acquisition blockers from signal-validation blockers."""
    if (
        not isinstance(readiness_report, dict)
        or readiness_report.get("stage") != 42
    ):
        raise ValueError("Stage 42 readiness report required")

    latest = readiness_report.get("latest_probe_status")
    budget = readiness_report.get("budget")
    credits = readiness_report.get("provider_credits")

    if not isinstance(budget, dict) or not isinstance(credits, dict):
        raise ValueError("Missing readiness evidence")

    if not isinstance(latest, str):
        raise ValueError("Missing probe status")

    if not isinstance(budget.get("status"), str):
        raise ValueError("Missing budget status")

    if not isinstance(credits.get("status"), str):
        raise ValueError("Missing credit status")

    steps = []

    def add(code, area, status, action):
        steps.append({
            "code": code,
            "area": area,
            "status": status,
            "action": action,
        })

    # An unresolved attempt may have consumed real provider credits.
    if latest != "VERIFIED":
        add(
            "REVIEW_UNRESOLVED_ATTEMPT",
            "ACQUISITION",
            "BLOCKED",
            "Inspect independent provider usage evidence for the "
            "latest attempt. Preserve the original journal. "
            "Do not automatically retry, relabel or reset it.",
        )
    else:
        add(
            "REVIEW_UNRESOLVED_ATTEMPT",
            "ACQUISITION",
            "REVIEWED_STATUS_ONLY",
            "Latest journal status is VERIFIED; ensure the "
            "original response evidence is independently valid.",
        )

    if budget["status"] != "LOCAL_CAPACITY":
        add(
            "CHECK_LOCAL_BUDGET",
            "ACQUISITION",
            "BLOCKED",
            "Inspect the existing reservation ledger and limits. "
            "Do not modify counters to create capacity.",
        )
    else:
        add(
            "CHECK_LOCAL_BUDGET",
            "ACQUISITION",
            "LOCAL_CAPACITY_ONLY",
            "Local capacity exists. This does not establish "
            "provider balance or authorize an API request.",
        )

    if credits["status"] != "RECENT_SNAPSHOT":
        add(
            "VERIFY_PROVIDER_CREDITS",
            "ACQUISITION",
            "BLOCKED",
            "Obtain a trustworthy current credit/usage statement "
            "through an approved, non-trading verification workflow. "
            "Do not assume stale counts are current.",
        )
    else:
        add(
            "VERIFY_PROVIDER_CREDITS",
            "ACQUISITION",
            "RECENT_SNAPSHOT_ONLY",
            "Credit snapshot is recent, but independently verify "
            "its source and meaning before authorizing collection.",
        )

    # These gates apply to analysis/accuracy, not merely to asking
    # a data provider for permission to retrieve market data.
    add(
        "VERIFY_DATA_PROVENANCE",
        "SIGNAL_VALIDATION",
        "PENDING",
        "Bind every completed candle dataset to a trustworthy "
        "provider response and retrieval timestamp.",
    )
    add(
        "VERIFY_FEED_MODE",
        "SIGNAL_VALIDATION",
        "PENDING",
        "Use authoritative provider evidence to distinguish "
        "live, delayed and unknown feed modes. Never guess LIVE.",
    )
    add(
        "CHECK_BROKER_PARITY",
        "SIGNAL_VALIDATION",
        "PENDING",
        "Compare aligned timestamps and prices against the "
        "intended broker instrument before claiming broker "
        "signal performance. OTC and forex feeds may differ.",
    )
    add(
        "RUN_INDEPENDENT_FORWARD_VALIDATION",
        "SIGNAL_VALIDATION",
        "PENDING",
        "Collect enough new completed candles and independent "
        "expiry outcomes. Report uncertainty, sample size, "
        "payout assumptions and NO TRADE frequency.",
    )

    acquisition_blockers = [
        s["code"] for s in steps
        if s["area"] == "ACQUISITION"
        and s["status"] == "BLOCKED"
    ]

    signal_blockers = [
        s["code"] for s in steps
        if s["area"] == "SIGNAL_VALIDATION"
        and s["status"] == "PENDING"
    ]

    return {
        "stage": 43,
        "latest_probe_status": latest,
        "acquisition": {
            "status": (
                "BLOCKED" if acquisition_blockers
                else "MANUAL_APPROVAL_STILL_REQUIRED"
            ),
            "blockers": acquisition_blockers,
            "api_request_approved": False,
        },
        "signal_validation": {
            "status": "BLOCKED",
            "blockers": signal_blockers,
            "directional_signals_approved": False,
        },
        "steps": steps,
        "recovery_rules": {
            "automatic_retry": False,
            "journal_reset": False,
            "counter_reset": False,
            "manual_status_promotion": False,
            "claim_live_from_csv_hash": False,
        },
        "api_requests_executed": 0,
        "analysis_only": True,
        "execution_enabled": False,
    }


def recovery_plan(
    *,
    probe=PROBE,
    budget=BUDGET,
    credits=CREDITS,
    csv=CSV,
    now=None,
):
    """Read existing local evidence through Stage 42."""
    assessment = readiness(
        probe=probe,
        budget=budget,
        credits=credits,
        csv=csv,
        now=now,
    )

    result = build_plan(assessment)

    result["checked_at_utc"] = assessment["checked_at_utc"]
    result["source_readiness_stage"] = assessment["stage"]

    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "action", nargs="?",
        choices=("plan", "export"),
        default="plan",
    )
    parser.add_argument("--probe", type=Path, default=PROBE)
    parser.add_argument("--budget", type=Path, default=BUDGET)
    parser.add_argument("--credits", type=Path, default=CREDITS)
    parser.add_argument("--csv", type=Path, default=CSV)
    parser.add_argument("--out", type=Path, default=OUT)

    args = parser.parse_args()

    try:
        result = recovery_plan(
            probe=args.probe,
            budget=args.budget,
            credits=args.credits,
            csv=args.csv,
        )

        print("=== STAGE 43 CONTROLLED RECOVERY PLAN ===")
        print(json.dumps(result, indent=2))

        if args.action == "export":
            path, created = write_evidence_report(
                result, args.out
            )
            print("report_path:", path)
            print("new_report_created:", created)

    except (OSError, ValueError, TypeError, KeyError) as exc:
        parser.exit(
            1,
            f"BLOCKED: {type(exc).__name__}. "
            "No API action was attempted.\n",
        )

    print("API requests: 0")
    print("Provider journal: UNCHANGED")
    print("Automatic recovery: DISABLED")
    print("Trading execution: DISABLED")


if __name__ == "__main__":
    main()
