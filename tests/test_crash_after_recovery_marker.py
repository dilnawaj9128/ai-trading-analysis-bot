import json
from datetime import datetime, timezone
from unittest.mock import patch

import pytest

from market_data.api_credit_monitor import CreditSnapshot
from market_data.authorization_journal import load_journal
from market_data.provider_credit_state import save_credit_state
from market_data.recovery_inspector import inspect_recovery_state
from market_data.unified_request_guard import authorize_request
from market_data.provider_credit_guard import ProviderCreditStatusUnknown


NOW = datetime(2026, 11, 13, 12, 0, tzinfo=timezone.utc)


def test_crash_after_marker_blocks_future_authorization(tmp_path):
    provider = tmp_path / "provider.json"
    budget = tmp_path / "budget.json"

    save_credit_state(
        CreditSnapshot(0, 100, False, True),
        path=provider,
        now=NOW,
    )

    marker_path = tmp_path / "provider.json.recovery_required.json"
    journal_path = tmp_path / "provider.json.authorization_journal.json"
    ledger_path = tmp_path / "provider.json.reservations.json"

    # Fail after recovery marker creation but before budget reserve.
    with patch(
        "market_data.unified_request_guard.reserve_request",
        side_effect=OSError("Simulated crash after marker"),
    ):
        with pytest.raises(
            OSError,
            match="Simulated crash after marker",
        ):
            authorize_request(
                provider_state_path=provider,
                local_budget_path=budget,
                now=NOW,
            )

    assert marker_path.exists()
    assert not ledger_path.exists()

    marker = json.loads(marker_path.read_text())
    journal = load_journal(journal_path)

    request_id = marker["request_id"]

    assert marker["recovery_required"] is True
    assert request_id in journal["transactions"]
    assert journal["transactions"][request_id]["status"] == "INTENT"

    marker_before = marker_path.read_bytes()
    journal_before = journal_path.read_bytes()

    inspection = inspect_recovery_state(provider)

    assert inspection.state == "INCONSISTENT"

    # Simulate next authorization attempt after restart.
    with pytest.raises(
        ProviderCreditStatusUnknown,
        match="recovery required",
    ):
        authorize_request(
            provider_state_path=provider,
            local_budget_path=budget,
            now=NOW,
        )

    # Recovery evidence must remain intact.
    assert marker_path.read_bytes() == marker_before
    assert journal_path.read_bytes() == journal_before
    assert not ledger_path.exists()
