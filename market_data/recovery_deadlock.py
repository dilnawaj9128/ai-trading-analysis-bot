"""Stage 52D Part 4D: offline recovery deadlock diagnosis.

No HTTP, no approval, no budget reservation, no journal writes.
"""

import json
from pathlib import Path

from market_data.recovery_preflight import evaluate_preflight


class RecoveryDeadlockError(RuntimeError):
    pass


def _read(path):
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise RecoveryDeadlockError(
            "Recovery evidence unavailable or corrupt"
        ) from exc

    if type(data) is not dict:
        raise RecoveryDeadlockError("Invalid recovery evidence")

    return data


def diagnose(*, root, case_path, archive_path, now=None):
    """Diagnose blocked routes without modifying evidence."""
    root = Path(root)

    preflight = evaluate_preflight(
        root=root,
        case_path=case_path,
        archive_path=archive_path,
        now=now,
    )

    probe = _read(root / "approved_research_probe.json")
    execution = _read(root / "credit_refresh_execution.json")
    lifecycle = _read(root / "credit_refresh_lifecycle.json")

    attempts = probe.get("attempts")

    if (
        probe.get("version") != 1
        or type(attempts) is not list
        or not attempts
        or type(attempts[-1]) is not dict
    ):
        raise RecoveryDeadlockError("Invalid probe history")

    latest = attempts[-1]
    probe_blocked = latest.get("status") != "VERIFIED"

    previous_refresh_claimed = (
        execution.get("status") in {
            "PREPARED",
            "RESERVATION_STARTED",
            "BUDGET_RESERVED",
            "REQUEST_ATTEMPTED",
            "UNCERTAIN",
        }
        or lifecycle.get("status") == "CLAIMED"
    )

    evidence_valid = (
        preflight["evidence_matches"]
        and preflight["original_still_uncertain"]
    )

    fresh_credits = preflight["fresh_provider_credits"]

    # This is a diagnosis, not an alternative network authorization.
    blocked_reasons = []

    if not evidence_valid:
        blocked_reasons.append("HISTORICAL_EVIDENCE_REVIEW_REQUIRED")

    if probe_blocked:
        blocked_reasons.append("EXISTING_PROBE_GATE_BLOCKS_HTTP")

    if previous_refresh_claimed:
        blocked_reasons.append("PREVIOUS_REFRESH_CANNOT_BE_REUSED")

    if not fresh_credits:
        blocked_reasons.append("FRESH_PROVIDER_CREDITS_UNAVAILABLE")

    if not preflight["local_budget_ok"]:
        blocked_reasons.append("LOCAL_BUDGET_NOT_READY")

    return {
        "stage": "52D_PART4D",
        "classification": "RECOVERY_ROUTE_REQUIRED",
        "reasons": blocked_reasons,
        "original_probe_status": latest.get("status"),
        "historical_evidence_valid": evidence_valid,
        "previous_refresh_claimed": previous_refresh_claimed,
        "fresh_provider_credits": fresh_credits,
        "local_budget_ok": preflight["local_budget_ok"],
        "normal_fetch_allowed": False,
        "recovery_http_implemented": False,
        "recovery_http_authorized": False,
        "old_request_retry_allowed": False,
        "trading_enabled": False,
    }
