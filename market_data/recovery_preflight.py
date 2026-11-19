"""Stage 52D Part 4A: offline recovery readiness preflight.

Read-only. Does not approve, reserve, settle, retry, or execute HTTP.
A READY result is only a prerequisite, NEVER network authorization.
"""

import json
from datetime import datetime, timezone
from pathlib import Path

from market_data.recovery_case import sha256_file
from market_data.provider_credit_state import load_credit_state
from market_data.twelve_data_client import (
    MINUTE_LIMIT,
    DAY_LIMIT,
    RESERVE_PER_REQUEST,
)


class RecoveryPreflightError(RuntimeError):
    pass


SOURCE_FILES = {
    "probe": "approved_research_probe.json",
    "execution": "credit_refresh_execution.json",
    "lifecycle": "credit_refresh_lifecycle.json",
    "provider": "provider_credits.json",
}


def _json(path):
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise RecoveryPreflightError(
            "Recovery evidence missing or invalid"
        ) from exc

    if type(data) is not dict:
        raise RecoveryPreflightError("Invalid evidence structure")

    return data


def evaluate_preflight(*, root, case_path, now=None, archive_path=None):
    """Evaluate evidence and quota without changing any files."""
    root = Path(root)
    now = now or datetime.now(timezone.utc)

    if now.tzinfo is None:
        raise RecoveryPreflightError("Timezone-aware time required")

    now = now.astimezone(timezone.utc)
    case = _json(case_path)

    if (
        case.get("schema_version") != 1
        or case.get("classification") != "UNRESOLVED_ACCOUNTING"
        or case.get("probe_status") != "UNCERTAIN"
    ):
        raise RecoveryPreflightError("Invalid recovery case")

    decision = case.get("decision")
    if (
        type(decision) is not dict
        or decision.get("old_request_verified") is not False
        or decision.get("new_api_request_authorized") is not False
        or decision.get("retry_allowed") is not False
    ):
        raise RecoveryPreflightError("Recovery case authorization invalid")

    fingerprints = case.get("source_sha256")
    if type(fingerprints) is not dict:
        raise RecoveryPreflightError("Missing source fingerprints")

    evidence_matches = True

    if archive_path is not None:
        archive_path = Path(archive_path)
        if archive_path.resolve() == (
            root / SOURCE_FILES["provider"]
        ).resolve():
            raise RecoveryPreflightError(
                "Historical archive must be separate"
            )

    for name, filename in SOURCE_FILES.items():
        expected = fingerprints.get(name)

        if (
            type(expected) is not str
            or len(expected) != 64
            or any(c not in "0123456789abcdef" for c in expected)
        ):
            raise RecoveryPreflightError("Invalid evidence fingerprint")

        source = (
            archive_path
            if name == "provider" and archive_path is not None
            else root / filename
        )
        try:
            actual = sha256_file(source)
        except OSError as exc:
            raise RecoveryPreflightError(
                "Recovery source unavailable"
            ) from exc

        if actual != expected:
            evidence_matches = False

    probe = _json(root / SOURCE_FILES["probe"])
    attempts = probe.get("attempts")

    if type(attempts) is not list or not attempts:
        raise RecoveryPreflightError("Invalid probe attempts")

    last = attempts[-1]

    if type(last) is not dict:
        raise RecoveryPreflightError("Invalid final probe")

    original_still_uncertain = (
        last.get("status") == "UNCERTAIN"
        and len(attempts) == case.get("probe_attempt_count")
        and last.get("started_at") == case.get("probe_started_at")
    )

    credits = load_credit_state(
        path=root / SOURCE_FILES["provider"],
        now=now,
        max_age_seconds=300,
    )

    fresh_credits = (
        credits is not None
        and credits.credits_left is not None
        and credits.credits_left >= RESERVE_PER_REQUEST
    )

    budget_path = root / "twelve_data_budget.json"

    # An absent budget is NOT considered proof of zero usage.
    if budget_path.exists():
        budget = _json(budget_path)
        minute = now.strftime("%Y-%m-%dT%H:%MZ")
        day = now.strftime("%Y-%m-%d")

        minute_used = (
            budget.get("minute_used")
            if budget.get("minute") == minute else 0
        )
        day_used = (
            budget.get("day_used")
            if budget.get("day") == day else 0
        )

        budget_ok = (
            type(minute_used) is int
            and type(day_used) is int
            and minute_used >= 0
            and day_used >= 0
            and minute_used + RESERVE_PER_REQUEST <= MINUTE_LIMIT
            and day_used + RESERVE_PER_REQUEST <= DAY_LIMIT
        )
    else:
        budget_ok = False

    reasons = []

    if not evidence_matches:
        reasons.append("EVIDENCE_FINGERPRINT_MISMATCH")

    if not original_still_uncertain:
        reasons.append("PROBE_HISTORY_CHANGED")

    if not fresh_credits:
        reasons.append("FRESH_PROVIDER_CREDITS_REQUIRED")

    if not budget_ok:
        reasons.append("LOCAL_BUDGET_UNAVAILABLE_OR_EXCEEDED")

    if not reasons:
        reasons.append("SEPARATE_RECOVERY_APPROVAL_REQUIRED")

    return {
        "stage": "52D_PART4A",
        "preflight": (
            "READY_FOR_APPROVAL_REVIEW"
            if reasons == ["SEPARATE_RECOVERY_APPROVAL_REQUIRED"]
            else "BLOCKED"
        ),
        "reasons": reasons,
        "evidence_matches": evidence_matches,
        "original_still_uncertain": original_still_uncertain,
        "fresh_provider_credits": fresh_credits,
        "local_budget_ok": budget_ok,
        "new_api_request_authorized": False,
        "retry_allowed": False,
        "trading_enabled": False,
    }
