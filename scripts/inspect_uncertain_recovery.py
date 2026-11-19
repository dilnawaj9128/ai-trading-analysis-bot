"""Read-only inspection of unresolved Twelve Data requests."""

import hashlib
import json
from pathlib import Path
from datetime import datetime, timezone

ROOT = Path("data/api_usage")


def load(name):
    path = ROOT / name
    if not path.is_file():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else None
    except (OSError, ValueError):
        return None


def inspect():
    probe = load("approved_research_probe.json")
    credits = load("provider_credits.json")
    execution = load("credit_refresh_execution.json")
    lifecycle = load("credit_refresh_lifecycle.json")

    print("=== STAGE 52D RECOVERY INSPECTION ===")

    if not probe or not isinstance(probe.get("attempts"), list):
        print("PROBE: INVALID_OR_MISSING")
        return False

    attempts = probe["attempts"]
    last = attempts[-1] if attempts else {}

    print("Probe attempts:", len(attempts))
    print("Last probe status:", last.get("status"))
    print("Failure category:", last.get("failure_category", "MISSING"))
    print("Failure timestamp:", last.get("last_failure_at", "MISSING"))

    csv_path = last.get("csv_path")
    expected_hash = last.get("csv_sha256")
    csv_verified = False

    if isinstance(csv_path, str) and isinstance(expected_hash, str):
        path = Path(csv_path)
        if path.is_file():
            csv_verified = (
                hashlib.sha256(path.read_bytes()).hexdigest()
                == expected_hash
            )

    print("Request-specific CSV hash verified:", csv_verified)

    if credits:
        print("Last credit observation:", credits.get("observed_at"))
        print("Last recorded credits:", credits.get("credits_left"))

        try:
            observed = datetime.fromisoformat(credits["observed_at"])
            age = (datetime.now(timezone.utc) - observed).total_seconds()
            print("Credit snapshot fresh:", 0 <= age <= 300)
        except (ValueError, TypeError, KeyError):
            print("Credit snapshot fresh: False")
    else:
        print("Provider credit snapshot: MISSING")

    print("Refresh execution:", (
        execution or {}
    ).get("status", "MISSING"))

    print("Refresh lifecycle:", (
        lifecycle or {}
    ).get("status", "MISSING"))

    if last.get("status") == "VERIFIED" and csv_verified:
        print("PROBE RESULT: VERIFIED_EVIDENCE_PRESENT")
    else:
        print("PROBE RESULT: RECONCILIATION_REQUIRED")

    print("NETWORK REQUESTS: 0")
    print("STATE FILES MODIFIED: 0")

    # Do not authorize or settle any request.
    return last.get("status") == "VERIFIED" and csv_verified


if __name__ == "__main__":
    inspect()
