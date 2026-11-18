"""Offline HTTP response evidence validation.

Validates local consistency only. Does not prove that a response
came from Twelve Data or authorize settlement/completion.
"""


def validate_response_evidence(
    *,
    request_id,
    reservation,
    journal_transaction,
    response_status,
    response_headers,
):
    if not isinstance(request_id, str) or len(request_id) != 32:
        raise ValueError("Invalid request ID")

    if any(c not in "0123456789abcdef" for c in request_id):
        raise ValueError("Invalid request ID")

    if not isinstance(reservation, dict):
        raise ValueError("Invalid reservation")

    if not isinstance(journal_transaction, dict):
        raise ValueError("Invalid journal transaction")

    if reservation.get("status") != "PENDING":
        raise ValueError("Reservation is not PENDING")

    if journal_transaction.get("status") != "FINALIZED":
        raise ValueError("Journal is not FINALIZED")

    credits = reservation.get("credits")

    if (
        type(credits) is not int
        or credits < 1
        or credits != journal_transaction.get("credits")
    ):
        raise ValueError("Credits mismatch")

    if reservation.get("authorized_at") != journal_transaction.get(
        "authorized_at"
    ):
        raise ValueError("Authorization timestamp mismatch")

    if type(response_status) is not int or not 200 <= response_status < 300:
        raise ValueError("HTTP response unsuccessful")

    if not hasattr(response_headers, "get"):
        raise ValueError("Invalid response headers")

    used = response_headers.get("api-credits-used")
    left = response_headers.get("api-credits-left")

    try:
        used = int(used)
        left = int(left)
    except (TypeError, ValueError) as exc:
        raise ValueError("Missing or invalid credit headers") from exc

    if used < 0 or left < 0:
        raise ValueError("Negative provider credits")

    return {
        "structurally_valid": True,
        "request_id": request_id,
        "provider_credits_used": used,
        "provider_credits_left": left,
        "trusted_provider_provenance": False,
        "settlement_authorized": False,
        "completion_authorized": False,
    }
