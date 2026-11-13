import json
from datetime import datetime, timedelta, timezone

from market_data.api_credit_monitor import CreditSnapshot
from market_data.provider_credit_state import save_credit_state
from market_data.unified_request_guard import authorize_request


NOW = datetime(2026, 11, 13, 12, 0, tzinfo=timezone.utc)


def test_authorization_records_snapshot_metadata(tmp_path):
    provider = tmp_path / "provider.json"
    budget = tmp_path / "budget.json"

    observed_at = NOW - timedelta(seconds=30)

    save_credit_state(
        CreditSnapshot(
            credits_used=5,
            credits_left=100,
            low_credits=False,
            information_available=True,
        ),
        path=provider,
        now=observed_at,
    )

    result = authorize_request(
        provider_state_path=provider,
        local_budget_path=budget,
        now=NOW,
    )

    ledger_path = tmp_path / "provider.json.reservations.json"

    ledger = json.loads(ledger_path.read_text())

    entry = ledger["requests"][result.request_id]

    assert entry["credits"] == 1
    assert entry["status"] == "PENDING"
    assert entry["authorized_at"] == NOW.isoformat()
    assert entry["snapshot_observed_at"] == observed_at.isoformat()
    assert ledger["reserved"] == 1


def test_multiple_requests_have_distinct_ids_and_metadata(tmp_path):
    provider = tmp_path / "provider.json"
    budget = tmp_path / "budget.json"

    save_credit_state(
        CreditSnapshot(
            credits_used=0,
            credits_left=100,
            low_credits=False,
            information_available=True,
        ),
        path=provider,
        now=NOW,
    )

    first = authorize_request(
        provider_state_path=provider,
        local_budget_path=budget,
        now=NOW,
    )

    second = authorize_request(
        provider_state_path=provider,
        local_budget_path=budget,
        now=NOW,
    )

    assert first.request_id != second.request_id

    ledger = json.loads(
        (tmp_path / "provider.json.reservations.json").read_text()
    )

    assert ledger["reserved"] == 2
    assert len(ledger["requests"]) == 2

    for request_id in (first.request_id, second.request_id):
        entry = ledger["requests"][request_id]

        assert entry["status"] == "PENDING"
        assert entry["authorized_at"] == NOW.isoformat()
        assert entry["snapshot_observed_at"] == NOW.isoformat()
