from concurrent.futures import ThreadPoolExecutor

import pytest

from market_data.reservation_lifecycle import ReservationStatus
from market_data.reservation_registry import (
    ReservationRegistryError,
    create_reservation,
    transition_reservation,
    get_outstanding_credits,
)


def test_create_persistent_reservation(tmp_path):
    path = tmp_path / "registry.json"

    item = create_reservation(path=path, credits=2)

    assert item.status == ReservationStatus.PENDING
    assert get_outstanding_credits(path=path) == 2


def test_settle_reservation(tmp_path):
    path = tmp_path / "registry.json"

    item = create_reservation(path=path, credits=2)

    updated = transition_reservation(
        path=path,
        request_id=item.request_id,
        status=ReservationStatus.SETTLED,
    )

    assert updated.status == ReservationStatus.SETTLED
    assert get_outstanding_credits(path=path) == 0


def test_uncertain_remains_outstanding(tmp_path):
    path = tmp_path / "registry.json"

    item = create_reservation(path=path, credits=3)

    transition_reservation(
        path=path,
        request_id=item.request_id,
        status=ReservationStatus.UNCERTAIN,
    )

    assert get_outstanding_credits(path=path) == 3


def test_duplicate_transition_rejected(tmp_path):
    path = tmp_path / "registry.json"

    item = create_reservation(path=path)

    transition_reservation(
        path=path,
        request_id=item.request_id,
        status=ReservationStatus.SETTLED,
    )

    with pytest.raises(ValueError):
        transition_reservation(
            path=path,
            request_id=item.request_id,
            status=ReservationStatus.SETTLED,
        )


def test_unknown_request_rejected(tmp_path):
    with pytest.raises(ReservationRegistryError):
        transition_reservation(
            path=tmp_path / "registry.json",
            request_id="missing",
            status=ReservationStatus.SETTLED,
        )


def test_concurrent_creation(tmp_path):
    path = tmp_path / "registry.json"

    def create(_):
        return create_reservation(path=path)

    with ThreadPoolExecutor(max_workers=8) as pool:
        items = list(pool.map(create, range(20)))

    assert len({item.request_id for item in items}) == 20
    assert get_outstanding_credits(path=path) == 20


def test_corrupted_registry_fails_closed(tmp_path):
    path = tmp_path / "registry.json"
    path.write_text("{invalid json")

    with pytest.raises(ReservationRegistryError):
        get_outstanding_credits(path=path)
