import json
from datetime import datetime, timezone
from unittest.mock import Mock

from market_data.api_credit_monitor import CreditSnapshot
from market_data.provider_credit_state import (
    load_credit_state,
    save_credit_state,
)
from market_data.credit_response_handler import (
    refresh_credits_from_response,
)
from market_data.unified_request_guard import authorize_request


NOW = datetime(2026, 11, 13, 12, 0, tzinfo=timezone.utc)


def test_refresh_preserves_outstanding_reservations(tmp_path):
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

    authorize_request(
        provider_state_path=provider,
        local_budget_path=budget,
        now=NOW,
    )

    ledger_path = tmp_path / "provider.json.reservations.json"
    before = json.loads(ledger_path.read_text())

    assert before["reserved"] == 1

    response = Mock()
    response.headers = {
        "api-credits-used": "1",
        "api-credits-left": "99",
    }

    result = refresh_credits_from_response(
        response,
        path=provider,
        now=NOW,
    )

    after = json.loads(ledger_path.read_text())

    assert result.updated is True
    assert after["reserved"] == 1

    snapshot = load_credit_state(path=provider, now=NOW)
    assert snapshot.credits_left == 99


def test_refresh_does_not_reset_multiple_reservations(tmp_path):
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

    for _ in range(2):
        authorize_request(
            provider_state_path=provider,
            local_budget_path=budget,
            now=NOW,
        )

    response = Mock()
    response.headers = {
        "api-credits-used": "1",
        "api-credits-left": "99",
    }

    refresh_credits_from_response(
        response,
        path=provider,
        now=NOW,
    )

    ledger_path = tmp_path / "provider.json.reservations.json"
    ledger = json.loads(ledger_path.read_text())

    assert ledger["reserved"] == 2

    snapshot = load_credit_state(path=provider, now=NOW)
    assert snapshot.credits_left == 99
