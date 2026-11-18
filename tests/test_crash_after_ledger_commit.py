import json
from datetime import datetime, timezone
from unittest.mock import patch

import pytest

from market_data.api_credit_monitor import CreditSnapshot
from market_data.authorization_journal import load_journal
from market_data.provider_credit_guard import ProviderCreditStatusUnknown
from market_data.provider_credit_state import save_credit_state
from market_data.recovery_inspector import inspect_recovery_state
from market_data.unified_request_guard import authorize_request


NOW = datetime(2026, 11, 13, 12, 0, tzinfo=timezone.utc)


def test_crash_after_ledger_commit_preserves_reservation(tmp_path):
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

    # Simulate failure after ledger commit, before journal finalization.
    with patch(
        "market_data.unified_request_guard.finalize_intent",
        side_effect=OSError("Simulated crash after ledger commit"),
    ):
        with pytest.raises(
            OSError,
            match="Simulated crash after ledger commit",
        ):
            authorize_request(
                provider_state_path=provider,
                local_budget_path=budget,
                now=NOW,
            )

    assert marker_path.exists()
    assert ledger_path.exists()

    marker = json.loads(marker_path.read_text())
    ledger = json.loads(ledger_path.read_text())
    journal = load_journal(journal_path)

    request_id = marker["request_id"]

    assert request_id in ledger["requests"]
    assert ledger["requests"][request_id]["status"] == "PENDING"
    assert ledger["requests"][request_id]["credits"] == marker["credits"]
    assert ledger["reserved"] == marker["credits"]
    assert journal["transactions"][request_id]["status"] == "INTENT"

    marker_before = marker_path.read_bytes()
    ledger_before = ledger_path.read_bytes()
    journal_before = journal_path.read_bytes()

    inspection = inspect_recovery_state(provider)

    assert inspection.state == "COMMITTED"
    assert inspection.request_id == request_id

    # A subsequent authorization must remain blocked.
    with pytest.raises(
        ProviderCreditStatusUnknown,
        match="recovery required",
    ):
        authorize_request(
            provider_state_path=provider,
            local_budget_path=budget,
            now=NOW,
        )

    assert marker_path.read_bytes() == marker_before
    assert ledger_path.read_bytes() == ledger_before
    assert journal_path.read_bytes() == journal_before
