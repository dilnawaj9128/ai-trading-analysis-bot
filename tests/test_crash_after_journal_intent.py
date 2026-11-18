from datetime import datetime, timezone
from unittest.mock import patch

import pytest

from market_data.api_credit_monitor import CreditSnapshot
from market_data.authorization_journal import (
    AuthorizationJournalError,
    load_journal,
)
from market_data.provider_credit_state import save_credit_state
from market_data.recovery_inspector import inspect_recovery_state
from market_data.unified_request_guard import authorize_request


NOW = datetime(2026, 11, 13, 12, 0, tzinfo=timezone.utc)


def test_crash_after_intent_blocks_future_authorization(tmp_path):
    provider = tmp_path / "provider.json"
    budget = tmp_path / "budget.json"

    save_credit_state(
        CreditSnapshot(0, 100, False, True),
        path=provider,
        now=NOW,
    )

    journal_path = tmp_path / "provider.json.authorization_journal.json"
    marker_path = tmp_path / "provider.json.recovery_required.json"
    ledger_path = tmp_path / "provider.json.reservations.json"

    # Simulate failure immediately after journal INTENT is saved.
    with patch(
        "market_data.unified_request_guard._create_recovery_marker",
        side_effect=OSError("Simulated crash after journal intent"),
    ):
        with pytest.raises(
            OSError,
            match="Simulated crash after journal intent",
        ):
            authorize_request(
                provider_state_path=provider,
                local_budget_path=budget,
                now=NOW,
            )

    journal = load_journal(journal_path)

    assert len(journal["transactions"]) == 1
    assert next(
        iter(journal["transactions"].values())
    )["status"] == "INTENT"

    assert not marker_path.exists()
    assert not ledger_path.exists()

    journal_before = journal_path.read_bytes()

    inspection = inspect_recovery_state(provider)

    assert inspection.state == "INCONSISTENT"

    # Simulate a new authorization attempt after restart.
    with pytest.raises(
        AuthorizationJournalError,
        match="missing journal or ledger evidence|unresolved journal intent",
    ):
        authorize_request(
            provider_state_path=provider,
            local_budget_path=budget,
            now=NOW,
        )

    assert journal_path.read_bytes() == journal_before
    assert not marker_path.exists()
    assert not ledger_path.exists()
