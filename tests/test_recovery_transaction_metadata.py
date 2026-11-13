import json
from datetime import datetime, timezone
from unittest.mock import patch

import pytest

from market_data.api_credit_monitor import CreditSnapshot
from market_data.provider_credit_state import save_credit_state
from market_data.unified_request_guard import authorize_request


NOW = datetime(2026, 11, 13, 12, 0, tzinfo=timezone.utc)


def setup_state(tmp_path):
    provider = tmp_path / "provider.json"
    budget = tmp_path / "budget.json"

    save_credit_state(
        CreditSnapshot(0, 100, False, True),
        path=provider,
        now=NOW,
    )

    return provider, budget


def test_recovery_marker_contains_transaction_metadata(tmp_path):
    provider, budget = setup_state(tmp_path)

    with patch(
        "market_data.unified_request_guard._save_json_atomic",
        side_effect=OSError("Simulated commit failure"),
    ):
        with pytest.raises(OSError, match="Simulated commit failure"):
            authorize_request(
                provider_state_path=provider,
                local_budget_path=budget,
                now=NOW,
            )

    marker = json.loads(
        (tmp_path / "provider.json.recovery_required.json").read_text()
    )

    assert marker["recovery_required"] is True
    assert isinstance(marker["request_id"], str)
    assert len(marker["request_id"]) == 32
    assert marker["authorized_at"] == NOW.isoformat()
    assert marker["credits"] == 1


def test_marker_and_ledger_share_request_id_on_cleanup_failure(tmp_path):
    provider, budget = setup_state(tmp_path)

    with patch(
        "market_data.unified_request_guard._clear_recovery_marker",
        side_effect=OSError("Simulated cleanup failure"),
    ):
        with pytest.raises(OSError, match="Simulated cleanup failure"):
            authorize_request(
                provider_state_path=provider,
                local_budget_path=budget,
                now=NOW,
            )

    marker = json.loads(
        (tmp_path / "provider.json.recovery_required.json").read_text()
    )

    ledger = json.loads(
        (tmp_path / "provider.json.reservations.json").read_text()
    )

    request_id = marker["request_id"]

    assert request_id in ledger["requests"]
    assert ledger["requests"][request_id]["credits"] == marker["credits"]
    assert ledger["requests"][request_id]["status"] == "PENDING"
