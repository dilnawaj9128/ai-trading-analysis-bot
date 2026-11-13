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

    return provider, budget


def test_ledger_commit_failure_creates_recovery_marker(tmp_path):
    provider, budget = setup_state(tmp_path)

    with patch(
        "market_data.unified_request_guard._save_json_atomic",
        side_effect=OSError("Simulated ledger disk failure"),
    ):
        with pytest.raises(OSError, match="Simulated ledger disk failure"):
            authorize_request(
                provider_state_path=provider,
                local_budget_path=budget,
                now=NOW,
            )

    state = json.loads(budget.read_text())
    assert state["minute_used"] == 1
    assert state["day_used"] == 1

    marker = tmp_path / "provider.json.recovery_required.json"

    assert marker.exists()

    payload = json.loads(marker.read_text())
    assert payload["recovery_required"] is True


def test_recovery_marker_blocks_future_authorization(tmp_path):
    provider, budget = setup_state(tmp_path)

    marker = tmp_path / "provider.json.recovery_required.json"

    marker.write_text(json.dumps({
        "recovery_required": True,
        "reason": "authorization_commit_uncertain",
    }))

    with pytest.raises(
        ProviderCreditStatusUnknown,
        match="recovery",
    ):
        authorize_request(
            provider_state_path=provider,
            local_budget_path=budget,
            now=NOW,
        )

    assert not budget.exists()
