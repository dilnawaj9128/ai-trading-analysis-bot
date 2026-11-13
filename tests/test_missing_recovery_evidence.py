import json
from datetime import datetime, timezone
from unittest.mock import patch

import pytest

from market_data.api_credit_monitor import CreditSnapshot
from market_data.provider_credit_state import save_credit_state
from market_data.recovery_inspector import inspect_recovery_state
from market_data.unified_request_guard import authorize_request


NOW = datetime(2026, 11, 13, 12, 0, tzinfo=timezone.utc)


def setup_state(tmp_path):
    provider = tmp_path / "provider.json"
    budget = tmp_path / "budget.json"
    marker = tmp_path / "provider.json.recovery_required.json"
    ledger = tmp_path / "provider.json.reservations.json"

    save_credit_state(
        CreditSnapshot(0, 100, False, True),
        path=provider,
        now=NOW,
    )

    return provider, budget, marker, ledger


def test_missing_marker_hides_uncommitted_transaction(tmp_path):
    provider, budget, marker, ledger = setup_state(tmp_path)

    with patch(
        "market_data.unified_request_guard._save_json_atomic",
        side_effect=OSError("Simulated ledger commit failure"),
    ):
        with pytest.raises(
            OSError,
            match="Simulated ledger commit failure",
        ):
            authorize_request(
                provider_state_path=provider,
                local_budget_path=budget,
                now=NOW,
            )

    assert marker.exists()
    assert budget.exists()
    assert not ledger.exists()

    before = json.loads(budget.read_text())
    assert before["minute_used"] == 1
    assert before["day_used"] == 1

    # Simulate accidental deletion of recovery evidence.
    marker.unlink()

    inspected = inspect_recovery_state(provider)

    # Missing recovery marker must not hide missing
    # authorization evidence.
    assert inspected.state == "INCONSISTENT"
    assert "missing" in inspected.reason.lower()

    after = json.loads(budget.read_text())
    assert after == before


def test_pending_ledger_entry_is_normal_without_marker(tmp_path):
    provider, budget, marker, ledger = setup_state(tmp_path)

    result = authorize_request(
        provider_state_path=provider,
        local_budget_path=budget,
        now=NOW,
    )

    assert result.authorized is True
    assert not marker.exists()

    state = json.loads(ledger.read_text())

    assert state["requests"][result.request_id]["status"] == "PENDING"
    assert inspect_recovery_state(provider).state == "NO_RECOVERY"
