import json
from datetime import datetime, timezone
from unittest.mock import patch

import pytest

from market_data.api_credit_monitor import CreditSnapshot
from market_data.provider_credit_state import save_credit_state
from market_data.unified_request_guard import authorize_request


NOW = datetime(2026, 11, 13, 12, 0, tzinfo=timezone.utc)


def test_journal_ledger_credit_mismatch_blocks_authorization(tmp_path):
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

    first = authorize_request(
        provider_state_path=provider,
        local_budget_path=budget,
        now=NOW,
    )

    assert first.authorized

    journal = json.loads(journal_path.read_text())

    journal["transactions"][first.request_id]["credits"] = 2

    journal_path.write_text(json.dumps(journal))

    before = budget.read_bytes()

    with patch(
        "market_data.unified_request_guard.reserve_request"
    ) as reserve:
        with pytest.raises(
            Exception,
            match="journal|ledger|mismatch",
        ):
            authorize_request(
                provider_state_path=provider,
                local_budget_path=budget,
                now=NOW,
            )

    reserve.assert_not_called()
    assert budget.read_bytes() == before
