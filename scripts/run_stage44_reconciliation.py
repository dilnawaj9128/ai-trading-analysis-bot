"""Stage 44: read-only provider usage reconciliation.

No API calls, no journal/credit changes, no automatic retry.
Manual dashboard snapshots remain unverified user-supplied evidence.
"""

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from scripts.run_stage41_evidence_audit import (
    load_probe,
    write_evidence_report,
)

PROBE = Path("data/api_usage/approved_research_probe.json")
EVIDENCE = Path("data/recovery/stage44_usage_evidence.json")
OUT = Path("data/recovery/stage44")

MAX_GAP_SECONDS = 6 * 3600


def parse_utc(value):
    if not isinstance(value, str):
        raise ValueError("Timestamp must be a string")
    result = datetime.fromisoformat(value)
    if result.tzinfo is None:
        raise ValueError("Timezone-aware timestamp required")
    return result.astimezone(timezone.utc)


def validate_snapshot(snapshot):
    if type(snapshot) is not dict:
        raise ValueError("Snapshot must be an object")

    if snapshot.get("source") != "provider_dashboard_manual":
        raise ValueError("Unsupported evidence source")

    observed = parse_utc(snapshot.get("observed_at"))

    used = snapshot.get("daily_credits_used")
    if type(used) is not int or used < 0:
        raise ValueError("Invalid daily credit count")

    usage_day = snapshot.get("usage_day")
    if (
        not isinstance(usage_day, str)
        or usage_day != observed.strftime("%Y-%m-%d")
    ):
        raise ValueError("Usage day must match observation UTC date")

    return observed, used, usage_day


def compare_usage(evidence, request_time):
    """Compare provider dashboard observations around one attempt.

    A delta shows an observed change, not attribution to the request.
    """
    if type(evidence) is not dict or evidence.get("version") != 1:
        raise ValueError("Invalid evidence format")

    before, before_used, before_day = validate_snapshot(
        evidence.get("before")
    )
    after, after_used, after_day = validate_snapshot(
        evidence.get("after")
    )

    if not before < request_time < after:
        raise ValueError("Snapshots must bracket request timestamp")

    if before_day != after_day:
        raise ValueError("Snapshots cross a usage-day boundary")

    if request_time.strftime("%Y-%m-%d") != before_day:
        raise ValueError("Request is outside usage day")

    if (
        (request_time - before).total_seconds() > MAX_GAP_SECONDS
        or (after - request_time).total_seconds() > MAX_GAP_SECONDS
    ):
        raise ValueError("Snapshots too far from request")

    delta = after_used - before_used

    if delta < 0:
        finding = "COUNTER_DECREASE_INCONCLUSIVE"
    elif delta == 0:
        finding = "NO_OBSERVABLE_USAGE_CHANGE"
    else:
        finding = "USAGE_INCREASE_NOT_ATTRIBUTABLE"

    return {
        "status": "COMPARED_UNVERIFIED_EVIDENCE",
        "finding": finding,
        "before_observed_at": before.isoformat(),
        "after_observed_at": after.isoformat(),
        "daily_credits_before": before_used,
        "daily_credits_after": after_used,
        "observed_delta": delta,
        "source": "provider_dashboard_manual",
        "independently_authenticated": False,
        "request_success_proven": False,
        "request_failure_proven": False,
    }


def reconcile(*, probe=PROBE, evidence=EVIDENCE):
    attempts = load_probe(probe)

    latest = attempts[-1] if attempts else None
    if latest is None:
        raise ValueError("No provider attempts recorded")

    status = latest["status"]
    request_time = parse_utc(latest["started_at"])

    comparison = {
        "status": "EVIDENCE_NOT_PROVIDED",
        "finding": "INCONCLUSIVE",
        "independently_authenticated": False,
        "request_success_proven": False,
        "request_failure_proven": False,
    }

    evidence_path = Path(evidence)

    if evidence_path.is_file():
        payload = json.loads(
            evidence_path.read_text(encoding="utf8")
        )
        comparison = compare_usage(payload, request_time)

    return {
        "stage": 44,
        "latest_attempt_number": len(attempts),
        "latest_attempt_status": status,
        "latest_attempt_started_at": request_time.isoformat(),
        "comparison": comparison,
        "reconciliation_status": (
            "MANUAL_REVIEW_REQUIRED"
            if status == "UNCERTAIN"
            else "NO_AUTOMATIC_RECONCILIATION"
        ),
        "provider_request_resolved": False,
        "journal_status_changed": False,
        "new_api_request_authorized": False,
        "feed_mode": "UNKNOWN",
        "directional_analysis_authorized": False,
        "api_requests_executed": 0,
        "analysis_only": True,
        "execution_enabled": False,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "action", nargs="?",
        choices=("audit", "export"), default="audit"
    )
    parser.add_argument("--probe", type=Path, default=PROBE)
    parser.add_argument("--evidence", type=Path, default=EVIDENCE)
    parser.add_argument("--out", type=Path, default=OUT)
    args = parser.parse_args()

    try:
        result = reconcile(
            probe=args.probe, evidence=args.evidence
        )

        print("=== STAGE 44 PROVIDER RECONCILIATION ===")
        print(json.dumps(result, indent=2))

        if args.action == "export":
            path, created = write_evidence_report(
                result, args.out
            )
            print("report_path:", path)
            print("new_report_created:", created)

    except (OSError, ValueError, KeyError, TypeError) as exc:
        parser.exit(
            1,
            f"BLOCKED: {type(exc).__name__}: {exc}\n"
            "No API call or journal update was made.\n"
        )

    print("API calls: 0")
    print("Journal changes: 0")
    print("Trading execution: DISABLED")


if __name__ == "__main__":
    main()
