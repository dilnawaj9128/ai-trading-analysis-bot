"""Offline credit-refresh safety regression tests."""

from market_data.credit_refresh_policy import decide_credit_refresh


def decide(**overrides):
    conditions = {
        "snapshot_status": "UNKNOWN",
        "explicitly_approved": True,
        "local_budget_available": True,
        "cooldown_satisfied": True,
        "recovery_required": False,
    }
    conditions.update(overrides)
    return decide_credit_refresh(**conditions)


def test_unknown_without_approval():
    result = decide(explicitly_approved=False)
    assert result.action != "ELIGIBLE"


def test_unknown_without_budget():
    result = decide(local_budget_available=False)
    assert result.action == "BLOCK"


def test_unknown_during_cooldown():
    result = decide(cooldown_satisfied=False)
    assert result.action == "BLOCK"


def test_unknown_during_recovery():
    result = decide(recovery_required=True)
    assert result.action == "BLOCK"


def test_fresh_snapshot_does_not_need_refresh():
    result = decide(snapshot_status="READY")
    assert result.action != "ELIGIBLE"


def test_eligible_is_only_a_decision():
    result = decide()
    assert result.action == "ELIGIBLE"
