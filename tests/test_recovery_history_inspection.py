from datetime import datetime, timezone

from market_data.api_credit_monitor import CreditSnapshot
from market_data.provider_credit_state import save_credit_state
from market_data.unified_request_guard import authorize_request
from market_data.recovery_inspector import inspect_recovery_state


NOW = datetime(2026, 11, 13, 12, 0, tzinfo=timezone.utc)


def test_missing_evidence_is_reported_as_inconsistent(tmp_path):
    provider = tmp_path / "provider.json"
    budget = tmp_path / "budget.json"

    journal = (
        tmp_path / "provider.json.authorization_journal.json"
    )
    ledger = (
        tmp_path / "provider.json.reservations.json"
    )
    history = (
        tmp_path / "provider.json.authorization_history.json"
    )

    save_credit_state(
        CreditSnapshot(0, 100, False, True),
        path=provider,
        now=NOW,
    )

    result = authorize_request(
        provider_state_path=provider,
        local_budget_path=budget,
        now=NOW,
    )

    assert result.authorized
    assert history.exists()

    journal.unlink()
    ledger.unlink()

    before = budget.read_bytes()

    inspection = inspect_recovery_state(provider)

    assert inspection.state == "INCONSISTENT"
    assert (
        "missing" in inspection.reason.lower()
        or "evidence" in inspection.reason.lower()
    )

    assert budget.read_bytes() == before
    assert not journal.exists()
    assert not ledger.exists()
