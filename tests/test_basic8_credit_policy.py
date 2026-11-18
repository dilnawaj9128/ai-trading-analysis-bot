import ast
from pathlib import Path

import pytest

from market_data.api_credit_monitor import CreditSnapshot
from market_data.basic8_credit_policy import (
    PROVIDER_RESERVE_CREDITS,
)
from market_data.provider_credit_guard import (
    ProviderCreditLimitReached,
    check_provider_credits,
)


def snapshot(remaining):
    return CreditSnapshot(
        credits_used=1,
        credits_left=remaining,
        low_credits=remaining < 20,
        information_available=True,
    )


def test_basic8_reserve_policy():
    assert PROVIDER_RESERVE_CREDITS == 1

    result = check_provider_credits(
        snapshot(7),
        required_credits=1,
        reserve_credits=PROVIDER_RESERVE_CREDITS,
    )
    assert result.allowed


def test_insufficient_credits_still_blocked():
    with pytest.raises(ProviderCreditLimitReached):
        check_provider_credits(
            snapshot(1),
            required_credits=1,
            reserve_credits=PROVIDER_RESERVE_CREDITS,
        )


@pytest.mark.parametrize(
    "filename",
    [
        "market_data/authorized_live_fetch.py",
        "market_data/historical_collector.py",
    ],
)
def test_fetch_paths_use_basic8_reserve(filename):
    tree = ast.parse(Path(filename).read_text())

    calls = [
        node for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "authorize_request"
    ]

    assert len(calls) == 1

    keywords = {
        keyword.arg: keyword.value
        for keyword in calls[0].keywords
    }

    reserve = keywords["reserve_credits"]

    assert isinstance(reserve, ast.Name)
    assert reserve.id == "PROVIDER_RESERVE_CREDITS"
