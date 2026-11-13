from datetime import datetime, timedelta, timezone

import pytest

from market_data.api_credit_monitor import CreditSnapshot
from market_data.credit_bootstrap_policy import decide_credit_bootstrap
from market_data.provider_credit_state import save_credit_state


NOW = datetime(2026, 11, 13, 12, 0, tzinfo=timezone.utc)


def make_state(tmp_path, left, observed_at=NOW):
    path = tmp_path / "credits.json"

    save_credit_state(
        CreditSnapshot(
            credits_used=5,
            credits_left=left,
            low_credits=left is not None and left < 20,
            information_available=left is not None,
        ),
        path=path,
        now=observed_at,
    )

    return path


def test_missing_state_requires_approval(tmp_path):
    result = decide_credit_bootstrap(
        path=tmp_path / "missing.json",
        now=NOW,
    )

    assert result.action == "REQUIRE_APPROVAL"
    assert result.requires_explicit_approval is True


def test_approved_bootstrap(tmp_path):
    result = decide_credit_bootstrap(
        path=tmp_path / "missing.json",
        now=NOW,
        bootstrap_approved=True,
    )

    assert result.action == "BOOTSTRAP"


def test_fresh_sufficient_credits(tmp_path):
    path = make_state(tmp_path, 100)

    result = decide_credit_bootstrap(path=path, now=NOW)

    assert result.action == "NORMAL"


def test_low_credits_blocked(tmp_path):
    path = make_state(tmp_path, 10)

    result = decide_credit_bootstrap(path=path, now=NOW)

    assert result.action == "BLOCK"


def test_low_credits_not_bypassed_by_approval(tmp_path):
    path = make_state(tmp_path, 10)

    result = decide_credit_bootstrap(
        path=path,
        now=NOW,
        bootstrap_approved=True,
    )

    assert result.action == "BLOCK"


def test_expired_state_requires_approval(tmp_path):
    path = make_state(
        tmp_path,
        100,
        observed_at=NOW - timedelta(minutes=10),
    )

    result = decide_credit_bootstrap(path=path, now=NOW)

    assert result.action == "REQUIRE_APPROVAL"


def test_expired_state_approved_bootstrap(tmp_path):
    path = make_state(
        tmp_path,
        100,
        observed_at=NOW - timedelta(minutes=10),
    )

    result = decide_credit_bootstrap(
        path=path,
        now=NOW,
        bootstrap_approved=True,
    )

    assert result.action == "BOOTSTRAP"


def test_unknown_remaining_requires_approval(tmp_path):
    path = make_state(tmp_path, None)

    result = decide_credit_bootstrap(path=path, now=NOW)

    assert result.action == "REQUIRE_APPROVAL"


def test_exact_credit_boundary(tmp_path):
    path = make_state(tmp_path, 21)

    result = decide_credit_bootstrap(path=path, now=NOW)

    assert result.action == "NORMAL"


@pytest.mark.parametrize("approval", [1, None, "yes"])
def test_invalid_approval(tmp_path, approval):
    with pytest.raises(ValueError):
        decide_credit_bootstrap(
            path=tmp_path / "missing.json",
            now=NOW,
            bootstrap_approved=approval,
        )
