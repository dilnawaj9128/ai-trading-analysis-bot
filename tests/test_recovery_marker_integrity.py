import json
from datetime import datetime, timezone
from unittest.mock import patch

import pytest

from market_data.api_credit_monitor import CreditSnapshot
from market_data.provider_credit_guard import ProviderCreditStatusUnknown
from market_data.provider_credit_state import save_credit_state
from market_data.recovery_inspector import inspect_recovery_state
from market_data.unified_request_guard import authorize_request


NOW = datetime(2026, 11, 13, 12, 0, tzinfo=timezone.utc)


def setup_state(tmp_path):
    provider = tmp_path / "provider.json"
    budget = tmp_path / "budget.json"
    marker = tmp_path / "provider.json.recovery_required.json"

    save_credit_state(
        CreditSnapshot(0, 100, False, True),
        path=provider,
        now=NOW,
    )

    (tmp_path / "provider.json.lock").touch()

    return provider, budget, marker


def valid_marker():
    return {
        "recovery_required": True,
        "reason": "authorization_commit_uncertain",
        "request_id": "a" * 32,
        "authorized_at": NOW.isoformat(),
        "credits": 1,
    }


def test_corrupt_marker_blocks_authorization(tmp_path):
    provider, budget, marker = setup_state(tmp_path)

    marker.write_text("{invalid json")

    inspected = inspect_recovery_state(provider)
    assert inspected.state == "INCONSISTENT"

    with patch(
        "market_data.unified_request_guard.reserve_request"
    ) as reserve:
        with pytest.raises(ProviderCreditStatusUnknown):
            authorize_request(
                provider_state_path=provider,
                local_budget_path=budget,
                now=NOW,
            )

    reserve.assert_not_called()
    assert marker.read_text() == "{invalid json"


@pytest.mark.parametrize(
    "change",
    [
        {"request_id": "invalid"},
        {"credits": 0},
        {"authorized_at": "not-a-date"},
        {"recovery_required": False},
    ],
)
def test_malformed_marker_blocks_authorization(
    tmp_path, change
):
    provider, budget, marker = setup_state(tmp_path)

    payload = valid_marker()
    payload.update(change)
    marker.write_text(json.dumps(payload))

    inspected = inspect_recovery_state(provider)
    assert inspected.state == "INCONSISTENT"

    with patch(
        "market_data.unified_request_guard.reserve_request"
    ) as reserve:
        with pytest.raises(ProviderCreditStatusUnknown):
            authorize_request(
                provider_state_path=provider,
                local_budget_path=budget,
                now=NOW,
            )

    reserve.assert_not_called()
    assert marker.exists()


def test_missing_marker_is_not_proof_of_safe_recovery(tmp_path):
    provider, budget, marker = setup_state(tmp_path)

    inspected = inspect_recovery_state(provider)

    assert inspected.state == "NO_RECOVERY"
    assert not marker.exists()
