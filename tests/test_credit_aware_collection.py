import pytest

from analysis.credit_aware_collection import (
    plan_credit_aware_collection,
)


START = "2026-11-12T10:00:00Z"
END = "2026-11-12T12:00:00Z"


def test_unknown_credits_remain_blocked():
    result = plan_credit_aware_collection(
        start=START,
        end=END,
    )

    assert result["budget_sufficient"] is False
    assert result["collection_authorized"] is False


def test_sufficient_estimated_credits_not_authorization():
    result = plan_credit_aware_collection(
        start=START,
        end=END,
        available_credits=100,
    )

    assert result["budget_sufficient"] is True
    assert result["collection_authorized"] is False


def test_low_credits():
    result = plan_credit_aware_collection(
        start=START,
        end=END,
        available_credits=0,
    )

    assert result["budget_sufficient"] is False


def test_invalid_credit_count():
    with pytest.raises(ValueError):
        plan_credit_aware_collection(
            start=START,
            end=END,
            available_credits=-1,
        )
