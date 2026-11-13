"""Pure reservation lifecycle transitions.

No network access, filesystem writes, or trading execution.
"""

from dataclasses import dataclass, replace
from enum import Enum


class ReservationStatus(str, Enum):
    PENDING = "PENDING"
    SETTLED = "SETTLED"
    UNCERTAIN = "UNCERTAIN"


@dataclass(frozen=True)
class CreditReservation:
    request_id: str
    credits: int
    status: ReservationStatus = ReservationStatus.PENDING

    def __post_init__(self):
        if not isinstance(self.request_id, str) or not self.request_id.strip():
            raise ValueError("request_id required")

        if type(self.credits) is not int or self.credits < 1:
            raise ValueError("credits must be positive")


def settle_reservation(reservation):
    """Mark a confirmed reservation as settled."""
    if not isinstance(reservation, CreditReservation):
        raise ValueError("CreditReservation required")

    if reservation.status != ReservationStatus.PENDING:
        raise ValueError("Only pending reservations can be settled")

    return replace(
        reservation,
        status=ReservationStatus.SETTLED,
    )


def mark_uncertain(reservation):
    """Keep uncertain requests accounted for."""
    if not isinstance(reservation, CreditReservation):
        raise ValueError("CreditReservation required")

    if reservation.status != ReservationStatus.PENDING:
        raise ValueError("Only pending reservations can become uncertain")

    return replace(
        reservation,
        status=ReservationStatus.UNCERTAIN,
    )


def outstanding_credits(reservations):
    """Count credits not conclusively reconciled."""
    return sum(
        item.credits
        for item in reservations
        if item.status in (
            ReservationStatus.PENDING,
            ReservationStatus.UNCERTAIN,
        )
    )
