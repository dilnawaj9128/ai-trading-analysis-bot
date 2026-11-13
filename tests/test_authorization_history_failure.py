from datetime import datetime, timezone
from unittest.mock import patch

import pytest

from market_data.api_credit_monitor import CreditSnapshot
from market_data.provider_credit_state import save_credit_state
from market_data.unified_request_guard import authorize_request


NOW = datetime(2026, 11, 13, 12, 0, tzinfo=timezone.utc)


def test_history_write_failure_blocks_budget_reservation(tmp_path):
    provider = tmp_path / "provider.json"
    budget = tmp_path / "budget.json"

    save_credit_state(
        CreditSnapshot(0, 100, False, True),
        path=provider,
        now=NOW,
    )

    with (
        patch(
            "market_data.unified_request_guard._save_authorization_history",
            side_effect=OSError("Simulated history write failure"),
        ),
        patch(
            "market_data.unified_request_guard.reserve_request"
        ) as reserve,
    ):
        with pytest.raises(
            OSError,
            match="Simulated history write failure",
        ):
            authorize_request(
                provider_state_path=provider,
                local_budget_path=budget,
                now=NOW,
            )

    reserve.assert_not_called()
    assert not budget.exists()
