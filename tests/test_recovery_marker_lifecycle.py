import json
from datetime import datetime, timezone
from unittest.mock import patch

import pytest

from market_data.api_credit_monitor import CreditSnapshot
from market_data.provider_credit_state import save_credit_state
from market_data.unified_request_guard import authorize_request
from market_data.provider_credit_guard import ProviderCreditStatusUnknown


NOW = datetime(2026, 11, 13, 12, 0, tzinfo=timezone.utc)


def setup_state(tmp_path):
    provider = tmp_path / "provider.json"
    budget = tmp_path / "budget.json"

    save_credit_state(
        CreditSnapshot(0, 100, False, True),
        path=provider,
        now=NOW,
    )

    marker = tmp_path / "provider.json.recovery_required.json"

    return provider, budget, marker


def test_successful_authorization_clears_marker(tmp_path):
    provider, budget, marker = setup_state(tmp_path)

    result = authorize_request(
        provider_state_path=provider,
        local_budget_path=budget,
        now=NOW,
    )

    assert result.authorized is True
    assert not marker.exists()


def test_budget_failure_preserves_recovery_marker(tmp_path):
    provider, budget, marker = setup_state(tmp_path)

    with patch(
        "market_data.unified_request_guard.reserve_request",
        side_effect=RuntimeError("Simulated budget failure"),
    ):
        with pytest.raises(RuntimeError, match="Simulated budget failure"):
            authorize_request(
                provider_state_path=provider,
                local_budget_path=budget,
                now=NOW,
            )

    assert marker.exists()


def test_existing_marker_blocks_budget_reservation(tmp_path):
    provider, budget, marker = setup_state(tmp_path)

    marker.write_text(json.dumps({
        "recovery_required": True,
        "reason": "authorization_commit_uncertain",
    }))

    with patch(
        "market_data.unified_request_guard.reserve_request"
    ) as reserve:
        with pytest.raises(
            ProviderCreditStatusUnknown,
            match="recovery",
        ):
            authorize_request(
                provider_state_path=provider,
                local_budget_path=budget,
                now=NOW,
            )

    reserve.assert_not_called()


def test_cleanup_failure_does_not_authorize(tmp_path):
    provider, budget, marker = setup_state(tmp_path)

    with patch(
        "market_data.unified_request_guard._clear_recovery_marker",
        side_effect=OSError("Simulated cleanup failure"),
    ):
        with pytest.raises(OSError, match="Simulated cleanup failure"):
            authorize_request(
                provider_state_path=provider,
                local_budget_path=budget,
                now=NOW,
            )

    assert marker.exists()

    ledger = json.loads(
        (tmp_path / "provider.json.reservations.json").read_text()
    )

    assert ledger["reserved"] == 1
