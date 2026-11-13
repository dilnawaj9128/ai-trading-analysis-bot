import pytest

from market_data.reservation_lifecycle import (
    CreditReservation,
    ReservationStatus,
    settle_reservation,
    mark_uncertain,
    outstanding_credits,
)


def test_new_reservation_is_pending():
    item = CreditReservation("request-1", 1)
    assert item.status == ReservationStatus.PENDING


def test_settlement():
    item = CreditReservation("request-1", 1)
    settled = settle_reservation(item)

    assert settled.status == ReservationStatus.SETTLED
    assert item.status == ReservationStatus.PENDING


def test_uncertain_reservation():
    item = CreditReservation("request-1", 2)
    uncertain = mark_uncertain(item)

    assert uncertain.status == ReservationStatus.UNCERTAIN
    assert outstanding_credits([uncertain]) == 2


def test_outstanding_excludes_settled():
    pending = CreditReservation("request-1", 2)
    settled = settle_reservation(
        CreditReservation("request-2", 3)
    )

    assert outstanding_credits([pending, settled]) == 2


def test_double_settlement_rejected():
    item = settle_reservation(
        CreditReservation("request-1", 1)
    )

    with pytest.raises(ValueError):
        settle_reservation(item)


def test_uncertain_cannot_be_directly_settled():
    item = mark_uncertain(
        CreditReservation("request-1", 1)
    )

    with pytest.raises(ValueError):
        settle_reservation(item)


@pytest.mark.parametrize("credits", [0, -1, True, 1.5])
def test_invalid_credit_amount(credits):
    with pytest.raises(ValueError):
        CreditReservation("request-1", credits)


def test_empty_request_id_rejected():
    with pytest.raises(ValueError):
        CreditReservation(" ", 1)
