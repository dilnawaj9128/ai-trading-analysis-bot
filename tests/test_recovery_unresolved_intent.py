import json
from datetime import datetime, timezone

from market_data.api_credit_monitor import CreditSnapshot
from market_data.provider_credit_state import save_credit_state
from market_data.unified_request_guard import authorize_request
from market_data.recovery_inspector import inspect_recovery_state


NOW = datetime(2026, 11, 13, 12, 0, tzinfo=timezone.utc)


def test_unresolved_intent_without_marker_is_inconsistent(tmp_path):
    provider = tmp_path / "provider.json"
    budget = tmp_path / "budget.json"

    journal_path = (
        tmp_path / "provider.json.authorization_journal.json"
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

    journal = json.loads(journal_path.read_text())
    journal["transactions"][result.request_id]["status"] = "INTENT"
    journal_path.write_text(json.dumps(journal))

    before = journal_path.read_bytes()

    inspection = inspect_recovery_state(provider)

    assert inspection.state == "INCONSISTENT"
    assert journal_path.read_bytes() == before
