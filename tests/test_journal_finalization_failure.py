import json
from datetime import datetime, timezone
from unittest.mock import patch

import pytest

from market_data.api_credit_monitor import CreditSnapshot
from market_data.provider_credit_state import save_credit_state
from market_data.unified_request_guard import authorize_request


NOW = datetime(2026, 11, 13, 12, 0, tzinfo=timezone.utc)


def test_finalization_failure_preserves_evidence_and_blocks_retry(tmp_path):
    provider = tmp_path / "provider.json"
    budget = tmp_path / "budget.json"

    journal = tmp_path / "provider.json.authorization_journal.json"
    ledger = tmp_path / "provider.json.reservations.json"
    marker = tmp_path / "provider.json.recovery_required.json"

    save_credit_state(
        CreditSnapshot(0, 100, False, True),
        path=provider,
        now=NOW,
    )

    with patch(
        "market_data.unified_request_guard.finalize_intent",
        side_effect=OSError("Simulated finalization failure"),
    ):
        with pytest.raises(
            OSError,
            match="Simulated finalization failure",
        ):
            authorize_request(
                provider_state_path=provider,
                local_budget_path=budget,
                now=NOW,
            )

    assert budget.exists()
    assert ledger.exists()
    assert marker.exists()
    assert journal.exists()

    ledger_data = json.loads(ledger.read_text())
    journal_data = json.loads(journal.read_text())

    assert ledger_data["reserved"] == 1
    assert len(ledger_data["requests"]) == 1

    request_id = next(iter(ledger_data["requests"]))

    assert ledger_data["requests"][request_id]["status"] == "PENDING"
    assert journal_data["transactions"][request_id]["status"] == "INTENT"

    before = budget.read_bytes()

    with patch(
        "market_data.unified_request_guard.reserve_request"
    ) as reserve:
        with pytest.raises(Exception, match="recovery|journal"):
            authorize_request(
                provider_state_path=provider,
                local_budget_path=budget,
                now=NOW,
            )

    reserve.assert_not_called()
    assert budget.read_bytes() == before
