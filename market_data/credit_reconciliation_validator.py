"""Offline structural checks for refresh evidence.

Passing these checks does NOT prove HTTP provenance,
authorize a request, or permit COMPLETED transition.
"""

from datetime import datetime, timezone


def _utc_timestamp(value):
    if not isinstance(value, str):
        raise ValueError("Timestamp must be a string")

    try:
        parsed = datetime.fromisoformat(
            value.replace("Z", "+00:00")
        )
    except ValueError as exc:
        raise ValueError("Invalid timestamp") from exc

    if parsed.tzinfo is None:
        raise ValueError("Timezone-aware timestamp required")

    return parsed.astimezone(timezone.utc)


def validate_reconciliation_candidate(attempt, evidence):
    if not isinstance(attempt, dict):
        raise ValueError("Invalid attempt")

    if not isinstance(evidence, dict):
        raise ValueError("Invalid evidence")

    if attempt.get("status") != "CLAIMED":
        raise ValueError("Attempt is not CLAIMED")

    attempt_id = attempt.get("attempt_id")

    if (
        not isinstance(attempt_id, str)
        or len(attempt_id) != 32
        or any(c not in "0123456789abcdef" for c in attempt_id)
    ):
        raise ValueError("Invalid attempt ID")

    if evidence.get("attempt_id") != attempt_id:
        raise ValueError("Attempt ID mismatch")

    attempted_at = _utc_timestamp(
        attempt.get("attempted_at")
    )
    observed_at = _utc_timestamp(
        evidence.get("observed_at")
    )

    if observed_at < attempted_at:
        raise ValueError("Evidence predates attempt")

    left = evidence.get("credits_left")

    if type(left) is not int or left < 0:
        raise ValueError("Invalid remaining credits")

    return {
        "structurally_valid": True,
        "verified_provider_provenance": False,
        "completion_authorized": False,
        "reason": (
            "Structural checks passed; trusted HTTP response "
            "binding and provider reconciliation still required"
        ),
    }
