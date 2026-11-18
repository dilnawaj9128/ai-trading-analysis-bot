import pytest

from market_data.authorization_ledger import (
    transition_authorization,
)
from market_data.credit_refresh_store import (
    transition_refresh_attempt,
)


def test_unverified_settlement_is_blocked(tmp_path):
    with pytest.raises(
        ValueError,
        match="Settlement requires verified reconciliation",
    ):
        transition_authorization(
            provider_state_path=tmp_path / "provider.json",
            request_id="test-request",
            status="SETTLED",
        )


def test_unverified_refresh_completion_is_blocked(tmp_path):
    with pytest.raises(
        ValueError,
        match="Completion requires verified provider reconciliation",
    ):
        transition_refresh_attempt(
            path=tmp_path / "refresh.json",
            attempt_id="a" * 32,
            status="COMPLETED",
        )
