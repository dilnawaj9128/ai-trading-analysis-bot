"""Stage 42: read-only provider and feed readiness checks.

No network calls, no API retries, no broker execution.
Does not approve any new request or modify existing state.
"""

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from market_data.twelve_data_client import (
    MINUTE_LIMIT, DAY_LIMIT
)
from scripts.run_stage41_evidence_audit import audit


PROBE = Path("data/api_usage/approved_research_probe.json")
BUDGET = Path("data/api_usage/twelve_data_budget.json")
CREDITS = Path("data/api_usage/provider_credits.json")
CSV = Path("data/real_market/latest_eurusd_completed.csv")


def utc_now():
    return datetime.now(timezone.utc)


def check_budget(path, now):
    """Read current local limits; never reserve or spend credits."""
    if not Path(path).is_file():
        return {"status": "UNKNOWN", "reason": "Budget ledger missing"}

    try:
        data = json.loads(Path(path).read_text(encoding="utf8"))

        if type(data) is not dict:
            raise ValueError("Invalid budget structure")

        minute = now.strftime("%Y-%m-%dT%H:%MZ")
        day = now.strftime("%Y-%m-%d")

        # Old periods have zero usage in the current period.
        minute_used = (
            data.get("minute_used", 0)
            if data.get("minute") == minute else 0
        )
        day_used = (
            data.get("day_used", 0)
            if data.get("day") == day else 0
        )

        if (
            type(minute_used) is not int
            or type(day_used) is not int
            or minute_used < 0
            or day_used < 0
        ):
            raise ValueError("Invalid budget counters")

        if minute_used >= MINUTE_LIMIT:
            return {
                "status": "BLOCKED",
                "reason": "Local minute budget exhausted",
            }

        if day_used >= DAY_LIMIT:
            return {
                "status": "BLOCKED",
                "reason": "Local daily budget exhausted",
            }

        return {
            "status": "LOCAL_CAPACITY",
            "minute_used": minute_used,
            "minute_limit": MINUTE_LIMIT,
            "day_used": day_used,
            "day_limit": DAY_LIMIT,
            "reason": "Local budget capacity only; not request approval",
        }

    except (OSError, ValueError, TypeError):
        return {
            "status": "BLOCKED",
            "reason": "Budget ledger unreadable or invalid",
        }


def check_provider_credits(path, now):
    """Check provider snapshot age without contacting provider."""
    if not Path(path).is_file():
        return {
            "status": "UNKNOWN",
            "reason": "Provider credit snapshot missing",
        }

    try:
        data = json.loads(Path(path).read_text(encoding="utf8"))

        if type(data) is not dict or data.get("version") != 1:
            raise ValueError("Invalid provider snapshot")

        observed = datetime.fromisoformat(data["observed_at"])

        if observed.tzinfo is None:
            raise ValueError("Timestamp timezone missing")

        observed = observed.astimezone(timezone.utc)
        age = (now - observed).total_seconds()

        credits_left = data.get("credits_left")

        if (
            type(credits_left) is not int
            or credits_left < 0
        ):
            raise ValueError("Invalid credit count")

        if age < 0 or age > 300:
            return {
                "status": "STALE",
                "reason": "Provider credit snapshot is not recent",
            }

        if credits_left == 0:
            return {
                "status": "BLOCKED",
                "reason": "Provider reports zero remaining credits",
            }

        return {
            "status": "RECENT_SNAPSHOT",
            "credits_left": credits_left,
            "reason": "Recent snapshot, not authorization",
        }

    except (OSError, ValueError, TypeError, KeyError):
        return {
            "status": "BLOCKED",
            "reason": "Provider credit snapshot invalid",
        }


def readiness(
    *,
    probe=PROBE,
    budget=BUDGET,
    credits=CREDITS,
    csv=CSV,
    now=None,
):
    now = now or utc_now()

    if now.tzinfo is None:
        raise ValueError("Timezone-aware evaluation required")

    now = now.astimezone(timezone.utc)

    try:
        evidence = audit(probe=probe, csv=csv)

        latest = evidence["latest_status"]
        attempt_safe = (
            latest == "VERIFIED"
            and not evidence["recovery_required"]
        )

    except (OSError, ValueError, TypeError, KeyError):
        latest = "UNKNOWN"
        attempt_safe = False

    budget_status = check_budget(budget, now)
    credit_status = check_provider_credits(credits, now)

    # Stage 41 does not independently establish live feed mode.
    feed_mode = "UNKNOWN"

    checks = {
        "latest_probe_verified": attempt_safe,
        "local_budget_capacity": (
            budget_status["status"] == "LOCAL_CAPACITY"
        ),
        "recent_provider_credit_snapshot": (
            credit_status["status"] == "RECENT_SNAPSHOT"
        ),
        "feed_mode_verified": False,
        "broker_parity_verified": False,
    }

    blockers = [
        key for key, passed in checks.items()
        if not passed
    ]

    # This stage never issues request authorization.
    return {
        "stage": 42,
        "checked_at_utc": now.isoformat(),
        "provider": "twelve_data",
        "latest_probe_status": latest,
        "budget": budget_status,
        "provider_credits": credit_status,
        "feed_mode": feed_mode,
        "checks": checks,
        "blockers": blockers,
        "collection_readiness": "BLOCKED",
        "new_api_request_authorized": False,
        "directional_analysis_authorized": False,
        "analysis_only": True,
        "execution_enabled": False,
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--probe", type=Path, default=PROBE)
    p.add_argument("--budget", type=Path, default=BUDGET)
    p.add_argument("--credits", type=Path, default=CREDITS)
    p.add_argument("--csv", type=Path, default=CSV)

    args = p.parse_args()

    result = readiness(
        probe=args.probe,
        budget=args.budget,
        credits=args.credits,
        csv=args.csv,
    )

    print("\n=== STAGE 42 FEED READINESS ===")
    print(json.dumps(result, indent=2))
    print("\nAPI requests: 0")
    print("Provider state changes: 0")
    print("Real trade execution: DISABLED")


if __name__ == "__main__":
    main()
