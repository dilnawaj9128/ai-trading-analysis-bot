import json
from datetime import datetime, timezone
from unittest.mock import patch

import pytest

from market_data.api_credit_monitor import CreditSnapshot
from market_data.provider_credit_state import save_credit_state
from market_data.unified_request_guard import authorize_request


NOW = datetime(2026, 11, 13, 12, 0, tzinfo=timezone.utc)


def test_failed_commit_preserves_independent_intent(tmp_path):
    provider = tmp_path / "provider.json"
    budget = tmp_path / "budget.json"

    marker = tmp_path / "provider.json.recovery_required.json"
    ledger = tmp_path / "provider.json.reservations.json"

    journal = tmp_path / "provider.json.authorization_journal.json"

    save_credit_state(
        CreditSnapshot(0, 100, False, True),
        path=provider,
        now=NOW,
    )

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

    # Simulate accidental marker deletion.
    marker.unlink()

    # New requirement: independent transaction evidence.
    assert journal.exists(), (
        "Missing durable authorization intent journal"
    )

    payload = json.loads(journal.read_text())

    assert payload["version"] == 1
    assert isinstance(payload["transactions"], dict)
    assert len(payload["transactions"]) == 1

    request_id, transaction = next(
        iter(payload["transactions"].items())
    )

    assert len(request_id) == 32
    assert transaction["credits"] == 1
    assert transaction["authorized_at"] == NOW.isoformat()
    assert transaction["status"] != "FINALIZED"


def test_unresolved_journal_blocks_next_authorization(tmp_path):
    provider = tmp_path / "provider.json"
    budget = tmp_path / "budget.json"
    marker = tmp_path / "provider.json.recovery_required.json"

    save_credit_state(
        CreditSnapshot(0, 100, False, True),
        path=provider,
        now=NOW,
    )

    with patch(
        "market_data.unified_request_guard._save_json_atomic",
        side_effect=OSError("Simulated ledger commit failure"),
    ):
        with pytest.raises(OSError):
            authorize_request(
                provider_state_path=provider,
                local_budget_path=budget,
                now=NOW,
            )

    marker.unlink()

    before = budget.read_bytes()

    with patch(
        "market_data.unified_request_guard.reserve_request"
    ) as reserve:
        with pytest.raises(Exception, match="journal|recovery"):
            authorize_request(
                provider_state_path=provider,
                local_budget_path=budget,
                now=NOW,
            )

    reserve.assert_not_called()
    assert budget.read_bytes() == before


def test_corrupt_journal_blocks_authorization(tmp_path):
    provider = tmp_path / "provider.json"
    budget = tmp_path / "budget.json"
    journal = (
        tmp_path / "provider.json.authorization_journal.json"
    )

    save_credit_state(
        CreditSnapshot(0, 100, False, True),
        path=provider,
        now=NOW,
    )

    journal.write_text("{invalid json")

    with patch(
        "market_data.unified_request_guard.reserve_request"
    ) as reserve:
        with pytest.raises(Exception, match="journal"):
            authorize_request(
                provider_state_path=provider,
                local_budget_path=budget,
                now=NOW,
            )

    reserve.assert_not_called()
    assert not budget.exists()


def test_deleted_journal_blocks_new_authorization(tmp_path):
    provider = tmp_path / "provider.json"
    budget = tmp_path / "budget.json"

    journal = (
        tmp_path / "provider.json.authorization_journal.json"
    )

    save_credit_state(
        CreditSnapshot(0, 100, False, True),
        path=provider,
        now=NOW,
    )

    first = authorize_request(
        provider_state_path=provider,
        local_budget_path=budget,
        now=NOW,
    )

    assert first.authorized
    assert journal.exists()

    journal.unlink()

    before = budget.read_bytes()

    with patch(
        "market_data.unified_request_guard.reserve_request"
    ) as reserve:
        with pytest.raises(
            Exception,
            match="journal|recovery",
        ):
            authorize_request(
                provider_state_path=provider,
                local_budget_path=budget,
                now=NOW,
            )

    reserve.assert_not_called()
    assert budget.read_bytes() == before
