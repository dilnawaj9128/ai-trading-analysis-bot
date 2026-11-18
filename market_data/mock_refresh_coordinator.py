"""Mock-only credit refresh workflow.

No production HTTP, real budget reservations, or trading execution.
"""

from dataclasses import dataclass

from market_data.request_response_evidence import (
    validate_response_evidence,
)


@dataclass(frozen=True)
class MockRefreshResult:
    status: str
    reason: str
    credits_left: int | None = None


def execute_mock_refresh(
    *,
    approved,
    cooldown_satisfied,
    budget_available,
    request_id,
    reservation,
    journal_transaction,
    response_callback,
):
    """Evaluate a simulated refresh using injected response data."""

    if approved is not True:
        return MockRefreshResult(
            "BLOCKED", "Explicit approval required"
        )

    if cooldown_satisfied is not True:
        return MockRefreshResult(
            "BLOCKED", "Refresh cooldown not satisfied"
        )

    if budget_available is not True:
        return MockRefreshResult(
            "BLOCKED", "Local budget unavailable"
        )

    if not callable(response_callback):
        return MockRefreshResult(
            "BLOCKED", "Response callback unavailable"
        )

    # Validate local request evidence before invoking callback.
    if not isinstance(reservation, dict):
        return MockRefreshResult(
            "BLOCKED", "Invalid reservation"
        )

    if not isinstance(journal_transaction, dict):
        return MockRefreshResult(
            "BLOCKED", "Invalid journal transaction"
        )

    if reservation.get("status") != "PENDING":
        return MockRefreshResult(
            "BLOCKED", "Reservation not pending"
        )

    if journal_transaction.get("status") != "FINALIZED":
        return MockRefreshResult(
            "BLOCKED", "Journal not finalized"
        )

    try:
        response = response_callback()

        evidence = validate_response_evidence(
            request_id=request_id,
            reservation=reservation,
            journal_transaction=journal_transaction,
            response_status=getattr(response, "status_code", None),
            response_headers=getattr(response, "headers", None),
        )

    except Exception:
        return MockRefreshResult(
            "UNCERTAIN",
            "Simulated request outcome unverified",
        )

    return MockRefreshResult(
        "VALIDATED_OFFLINE",
        "Response structure valid; provider provenance unverified",
        evidence["provider_credits_left"],
    )
