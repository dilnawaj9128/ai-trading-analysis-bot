from datetime import datetime, timezone

import pytest

from market_data.manual_refresh_preparation import (
    prepare_manual_refresh,
)
from market_data.manual_refresh_execution_state import (
    ExecutionStateError,
    create_execution,
    reserve_execution_budget,
    record_request_attempt,
    mark_uncertain,
)


NOW = datetime(2026, 11, 18, 12, 0, tzinfo=timezone.utc)


def prepared(tmp_path):
    approval = tmp_path / "approval.json"
    lifecycle = tmp_path / "lifecycle.json"
    execution = tmp_path / "execution.json"

    prepare_manual_refresh(
        approval_id="stage22f",
        approval_path=approval,
        lifecycle_path=lifecycle,
        explicitly_approved=True,
        now=NOW,
    )

    create_execution(
        approval_path=approval,
        lifecycle_path=lifecycle,
        approval_id="stage22f",
        execution_path=execution,
    )

    return approval, lifecycle, execution


def test_execution_starts_prepared(tmp_path):
    _, _, execution = prepared(tmp_path)

    assert execution.exists()
    assert '"PREPARED"' in execution.read_text()


def test_duplicate_execution_is_blocked(tmp_path):
    approval, lifecycle, execution = prepared(tmp_path)

    with pytest.raises(
        ExecutionStateError,
        match="already exists",
    ):
        create_execution(
            approval_path=approval,
            lifecycle_path=lifecycle,
            approval_id="stage22f",
            execution_path=execution,
        )


def test_budget_reserved_only_once(tmp_path):
    _, _, execution = prepared(tmp_path)
    budget = tmp_path / "budget.json"

    result = reserve_execution_budget(
        execution_path=execution,
        budget_path=budget,
        now=NOW,
    )

    assert result["status"] == "BUDGET_RESERVED"

    with pytest.raises(ExecutionStateError):
        reserve_execution_budget(
            execution_path=execution,
            budget_path=budget,
            now=NOW,
        )


def test_request_attempt_does_not_execute_http(tmp_path):
    _, _, execution = prepared(tmp_path)

    reserve_execution_budget(
        execution_path=execution,
        budget_path=tmp_path / "budget.json",
        now=NOW,
    )

    result = record_request_attempt(
        execution_path=execution
    )

    assert result["status"] == "REQUEST_ATTEMPTED"


def test_uncertain_request_cannot_be_retried(tmp_path):
    _, _, execution = prepared(tmp_path)

    reserve_execution_budget(
        execution_path=execution,
        budget_path=tmp_path / "budget.json",
        now=NOW,
    )

    record_request_attempt(execution_path=execution)
    mark_uncertain(execution_path=execution)

    with pytest.raises(ExecutionStateError):
        record_request_attempt(execution_path=execution)
