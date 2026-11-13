from datetime import datetime, timedelta, timezone

import pytest

from market_data.api_credit_monitor import CreditSnapshot
from market_data.provider_credit_state import (
    load_credit_state,
    save_credit_state,
)


NOW = datetime(2026, 11, 13, 12, 0, tzinfo=timezone.utc)


def snapshot(left=100):
    return CreditSnapshot(
        credits_used=5,
        credits_left=left,
        low_credits=False,
        information_available=True,
    )


def test_save_and_load(tmp_path):
    path = tmp_path / "credits.json"

    save_credit_state(snapshot(), path=path, now=NOW)
    result = load_credit_state(path=path, now=NOW)

    assert result.credits_left == 100
    assert result.credits_used == 5


def test_missing_file(tmp_path):
    result = load_credit_state(
        path=tmp_path / "missing.json",
        now=NOW,
    )

    assert result is None


def test_expired_state(tmp_path):
    path = tmp_path / "credits.json"

    save_credit_state(
        snapshot(),
        path=path,
        now=NOW - timedelta(minutes=10),
    )

    assert load_credit_state(path=path, now=NOW) is None


def test_fresh_state(tmp_path):
    path = tmp_path / "credits.json"

    save_credit_state(
        snapshot(50),
        path=path,
        now=NOW - timedelta(seconds=60),
    )

    result = load_credit_state(path=path, now=NOW)

    assert result.credits_left == 50


def test_corrupted_json(tmp_path):
    path = tmp_path / "credits.json"
    path.write_text("{invalid json")

    with pytest.raises(ValueError):
        load_credit_state(path=path, now=NOW)


def test_negative_credits_rejected(tmp_path):
    with pytest.raises(ValueError):
        save_credit_state(
            snapshot(-1),
            path=tmp_path / "credits.json",
            now=NOW,
        )


def test_future_timestamp_rejected(tmp_path):
    path = tmp_path / "credits.json"

    save_credit_state(
        snapshot(),
        path=path,
        now=NOW + timedelta(minutes=1),
    )

    assert load_credit_state(path=path, now=NOW) is None


def test_low_credit_status_restored(tmp_path):
    path = tmp_path / "credits.json"

    save_credit_state(snapshot(10), path=path, now=NOW)

    result = load_credit_state(path=path, now=NOW)

    assert result.low_credits is True


@pytest.mark.parametrize("max_age", [-1, True, 1.5])
def test_invalid_max_age(tmp_path, max_age):
    with pytest.raises(ValueError):
        load_credit_state(
            path=tmp_path / "credits.json",
            now=NOW,
            max_age_seconds=max_age,
        )
