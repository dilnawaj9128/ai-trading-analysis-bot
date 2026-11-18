import pytest

from market_data.credit_refresh_policy import decide_credit_refresh


def decision(status, **kwargs):
    return decide_credit_refresh(
        snapshot_status=status,
        **kwargs,
    )


def test_ready_does_not_refresh():
    result = decision("READY")
    assert result.action == "NO_REFRESH"


def test_low_credits_blocks():
    result = decision(
        "LOW_CREDITS",
        explicitly_approved=True,
        local_budget_available=True,
        cooldown_satisfied=True,
    )
    assert result.action == "BLOCK"


def test_unknown_requires_approval():
    result = decision(
        "UNKNOWN",
        local_budget_available=True,
        cooldown_satisfied=True,
    )
    assert result.action == "REQUIRE_APPROVAL"
    assert result.requires_approval is True


def test_unknown_approved_is_eligible():
    result = decision(
        "UNKNOWN",
        explicitly_approved=True,
        local_budget_available=True,
        cooldown_satisfied=True,
    )
    assert result.action == "ELIGIBLE"


def test_missing_budget_blocks():
    result = decision(
        "UNKNOWN",
        explicitly_approved=True,
        cooldown_satisfied=True,
    )
    assert result.action == "BLOCK"


def test_cooldown_blocks():
    result = decision(
        "UNKNOWN",
        explicitly_approved=True,
        local_budget_available=True,
    )
    assert result.action == "BLOCK"


def test_recovery_required_blocks():
    result = decision(
        "UNKNOWN",
        explicitly_approved=True,
        local_budget_available=True,
        cooldown_satisfied=True,
        recovery_required=True,
    )
    assert result.action == "BLOCK"


@pytest.mark.parametrize(
    "status",
    ["INVALID", "", "EXPIRED"],
)
def test_invalid_status_rejected(status):
    with pytest.raises(ValueError):
        decision(status)


def test_invalid_boolean_rejected():
    with pytest.raises(ValueError):
        decision(
            "UNKNOWN",
            explicitly_approved=1,
        )
