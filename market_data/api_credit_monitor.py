"""Read-only provider API credit monitoring."""

from dataclasses import dataclass
from collections.abc import Mapping


@dataclass(frozen=True)
class CreditSnapshot:
    credits_used: int | None
    credits_left: int | None
    low_credits: bool
    information_available: bool


def _parse_credit(value):
    if value is None:
        return None

    try:
        number = int(value)
    except (ValueError, TypeError):
        return None

    if number < 0:
        return None

    return number


def parse_credit_headers(
    headers: Mapping,
    *,
    minimum_remaining: int = 20,
) -> CreditSnapshot:

    if type(minimum_remaining) is not int or minimum_remaining < 0:
        raise ValueError("Invalid minimum_remaining")

    normalized = {
        str(key).lower(): value
        for key, value in headers.items()
    }

    used = _parse_credit(
        normalized.get("api-credits-used")
    )

    left = _parse_credit(
        normalized.get("api-credits-left")
    )

    return CreditSnapshot(
        credits_used=used,
        credits_left=left,
        low_credits=(
            left is not None and left < minimum_remaining
        ),
        information_available=(
            used is not None or left is not None
        ),
    )
