from datetime import datetime, timezone
from unittest.mock import patch

import pytest

from market_data.api_credit_monitor import CreditSnapshot
from market_data.provider_credit_state import save_credit_state
from market_data.unified_request_guard import authorize_request


NOW = datetime(2026, 11, 13, 12, 0, tzinfo=timezone.utc)


def test_journal_write_failure_prevents_budget_reservation(tmp_path):
    provider = tmp_path / "provider.json"
    budget = tmp_path / "budget.json"

    save_credit_state(
        CreditSnapshot(0, 100, False, True),
        path=provider,
        now=NOW,
    )

    with (
        patch(
            "market_data.authorization_journal.save_journal",
            side_effect=OSError("Simulated journal write failure"),
        ),
        patch(
            "market_data.unified_request_guard.reserve_request"
        ) as reserve,
    ):
        with pytest.raises(
            OSError,
            match="Simulated journal write failure",
        ):
            authorize_request(
                provider_state_path=provider,
                local_budget_path=budget,
                now=NOW,
            )

    reserve.assert_not_called()
    assert not budget.exists()


def test_failed_journal_write_does_not_create_recovery_marker(tmp_path):
    provider = tmp_path / "provider.json"
    budget = tmp_path / "budget.json"
    marker = (
        tmp_path / "provider.json.recovery_required.json"
    )

    save_credit_state(
        CreditSnapshot(0, 100, False, True),
        path=provider,
        now=NOW,
    )

    with patch(
        "market_data.authorization_journal.save_journal",
        side_effect=OSError("Simulated journal write failure"),
    ):
        with pytest.raises(OSError):
            authorize_request(
                provider_state_path=provider,
                local_budget_path=budget,
                now=NOW,
            )

    assert not marker.exists()
    assert not budget.exists()
