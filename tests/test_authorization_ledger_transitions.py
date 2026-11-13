import json
from datetime import datetime, timezone

import pytest

from market_data.api_credit_monitor import CreditSnapshot
from market_data.provider_credit_state import save_credit_state
from market_data.unified_request_guard import authorize_request
from market_data.authorization_ledger import (
    transition_authorization,
)


NOW = datetime(2026, 11, 13, 12, 0, tzinfo=timezone.utc)


def setup_authorization(tmp_path):
    provider = tmp_path / "provider.json"

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

    result = authorize_request(
        provider_state_path=provider,
        local_budget_path=tmp_path / "budget.json",
        now=NOW,
    )

    return provider, result.request_id


def test_mark_uncertain_preserves_reserved_credits(tmp_path):
    provider, request_id = setup_authorization(tmp_path)

    transition_authorization(
        provider_state_path=provider,
        request_id=request_id,
        status="UNCERTAIN",
    )

    ledger = json.loads(
        (tmp_path / "provider.json.reservations.json").read_text()
    )

    assert ledger["requests"][request_id]["status"] == "UNCERTAIN"
    assert ledger["reserved"] == 1


def test_unverified_settlement_preserves_reservation(tmp_path):
    provider, request_id = setup_authorization(tmp_path)

    with pytest.raises(
        ValueError,
        match="Settlement requires verified reconciliation",
    ):
        transition_authorization(
            provider_state_path=provider,
            request_id=request_id,
            status="SETTLED",
        )

    ledger = json.loads(
        (tmp_path / "provider.json.reservations.json").read_text()
    )

    assert ledger["requests"][request_id]["status"] == "PENDING"
    assert ledger["reserved"] == 1


def test_unknown_request_rejected(tmp_path):
    provider, _ = setup_authorization(tmp_path)

    with pytest.raises(ValueError):
        transition_authorization(
            provider_state_path=provider,
            request_id="unknown",
            status="SETTLED",
        )


def test_repeated_unverified_settlement_rejected(tmp_path):
    provider, request_id = setup_authorization(tmp_path)

    for _ in range(2):
        with pytest.raises(
            ValueError,
            match="Settlement requires verified reconciliation",
        ):
            transition_authorization(
                provider_state_path=provider,
                request_id=request_id,
                status="SETTLED",
            )

    ledger = json.loads(
        (tmp_path / "provider.json.reservations.json").read_text()
    )

    assert ledger["requests"][request_id]["status"] == "PENDING"
    assert ledger["reserved"] == 1
