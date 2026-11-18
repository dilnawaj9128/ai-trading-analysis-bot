import json
from datetime import datetime, timezone

import pytest

from market_data.manual_refresh_preparation import (
    prepare_manual_refresh,
)
from market_data.manual_refresh_execution_state import (
    ExecutionStateError,
)
from market_data.manual_credit_refresh import (
    ManualRefreshBlocked,
    prepare_and_record_refresh_offline,
)

NOW = datetime(2026, 11, 18, 12, 0, tzinfo=timezone.utc)


def setup(tmp_path):
    approval = tmp_path / "approval.json"
    lifecycle = tmp_path / "lifecycle.json"

    prepare_manual_refresh(
        approval_id="stage22i",
        approval_path=approval,
        lifecycle_path=lifecycle,
        explicitly_approved=True,
        now=NOW,
    )

    return {
        "approval_path": approval,
        "lifecycle_path": lifecycle,
        "approval_id": "stage22i",
        "execution_path": tmp_path / "execution.json",
        "budget_path": tmp_path / "budget.json",
        "now": NOW,
    }


def test_offline_preparation_does_not_reserve_budget(tmp_path):
    args = setup(tmp_path)

    result = prepare_and_record_refresh_offline(**args)

    assert result["status"] == "PREPARED"
    assert result["budget_reserved"] is False
    assert result["http_executed"] is False
    assert result["settlement_authorized"] is False

    execution = json.loads(
        args["execution_path"].read_text()
    )

    assert execution["status"] == "PREPARED"
    assert not args["budget_path"].exists()


def test_duplicate_preparation_is_blocked(tmp_path):
    args = setup(tmp_path)

    prepare_and_record_refresh_offline(**args)

    with pytest.raises(ExecutionStateError):
        prepare_and_record_refresh_offline(**args)

    assert not args["budget_path"].exists()


def test_production_budget_is_blocked(tmp_path):
    from market_data.twelve_data_client import STATE_PATH

    args = setup(tmp_path)
    args["budget_path"] = STATE_PATH

    with pytest.raises(
        ManualRefreshBlocked,
        match="Production execution authorization",
    ):
        prepare_and_record_refresh_offline(**args)

    assert not args["execution_path"].exists()
