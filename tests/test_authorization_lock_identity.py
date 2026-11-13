import fcntl
import os
from datetime import datetime, timezone
from unittest.mock import patch

import pytest

from market_data.api_credit_monitor import CreditSnapshot
from market_data.provider_credit_state import save_credit_state
from market_data.unified_request_guard import authorize_request


NOW = datetime(2026, 11, 13, 12, 0, tzinfo=timezone.utc)


def test_replaced_authorization_lock_blocks_budget(tmp_path):
    provider = tmp_path / "provider.json"
    budget = tmp_path / "budget.json"
    lock = tmp_path / "provider.json.lock"

    save_credit_state(
        CreditSnapshot(0, 100, False, True),
        path=provider,
        now=NOW,
    )

    real_flock = fcntl.flock
    replaced = False

    def replace_after_lock(fd, operation):
        nonlocal replaced

        result = real_flock(fd, operation)

        if operation == fcntl.LOCK_EX and not replaced:
            replaced = True

            replacement = tmp_path / "replacement.lock"
            replacement.touch()
            os.replace(replacement, lock)

        return result

    with patch(
        "market_data.unified_request_guard.fcntl.flock",
        side_effect=replace_after_lock,
    ):
        with pytest.raises(
            RuntimeError,
            match="lock identity",
        ):
            authorize_request(
                provider_state_path=provider,
                local_budget_path=budget,
                now=NOW,
            )

    assert replaced is True
    assert not budget.exists()
    assert not (
        tmp_path / "provider.json.recovery_required.json"
    ).exists()
