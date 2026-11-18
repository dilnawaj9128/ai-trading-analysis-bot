"""Offline refresh-to-request binding validation.

This module does not make HTTP requests, authorize requests,
settle reservations, or complete refresh attempts.
"""

from datetime import datetime, timezone


def _parse_utc(value):
    if not isinstance(value, str):
        raise ValueError("Timestamp must be a string")

    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise ValueError("Invalid timestamp") from exc

    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("Timezone-aware timestamp required")

    return parsed.astimezone(timezone.utc)


def _valid_id(value):
    return (
        isinstance(value, str)
        and len(value) == 32
        and all(char in "0123456789abcdef" for char in value)
    )


def validate_refresh_request_binding(
    *,
    attempt,
    approval_id,
    request_id,
    reservation,
    journal_transaction,
):
    """Check structural identity and reservation consistency."""

    if not isinstance(attempt, dict):
        raise ValueError("Invalid refresh attempt")

    if not isinstance(reservation, dict):
        raise ValueError("Invalid request reservation")

    if not isinstance(journal_transaction, dict):
        raise ValueError("Invalid journal transaction")

    attempt_id = attempt.get("attempt_id")

    if not _valid_id(attempt_id):
        raise ValueError("Invalid attempt ID")

    if attempt.get("status") != "CLAIMED":
        raise ValueError("Refresh attempt is not CLAIMED")

    if not isinstance(approval_id, str) or not approval_id.strip():
        raise ValueError("Invalid approval ID")

    if not _valid_id(request_id):
        raise ValueError("Invalid request ID")

    if reservation.get("status") != "PENDING":
        raise ValueError("Reservation must be PENDING")

    if journal_transaction.get("status") != "FINALIZED":
        raise ValueError("Journal transaction must be FINALIZED")

    reserved = reservation.get("credits")
    journal_credits = journal_transaction.get("credits")

    if (
        type(reserved) is not int
        or reserved < 1
        or reserved != journal_credits
    ):
        raise ValueError("Credit amount mismatch")

    attempt_time = _parse_utc(attempt.get("attempted_at"))
    request_time = _parse_utc(reservation.get("authorized_at"))
    journal_time = _parse_utc(
        journal_transaction.get("authorized_at")
    )

    if request_time != journal_time:
        raise ValueError("Authorization timestamp mismatch")

    if request_time < attempt_time:
        raise ValueError("Request predates refresh attempt")

    return {
        "structurally_valid": True,
        "attempt_id": attempt_id,
        "request_id": request_id,
        "approval_id": approval_id,
        "reserved_credits": reserved,
        "trusted_response_verified": False,
        "settlement_authorized": False,
        "completion_authorized": False,
    }
