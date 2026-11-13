from datetime import datetime, timezone
from unittest.mock import Mock, patch

import pytest

from market_data.api_credit_monitor import CreditSnapshot
from market_data.bootstrap_authorization import (
    BootstrapApprovalAlreadyUsed,
)
from market_data.bootstrap_request_coordinator import (
    BootstrapNotPermitted,
    execute_bootstrap,
)
from market_data.provider_credit_state import (
    load_credit_state,
    save_credit_state,
)


NOW = datetime(2026, 11, 13, 12, 0, tzinfo=timezone.utc)


def paths(tmp_path):
    return {
        "approval_path": tmp_path / "claim.json",
        "provider_state_path": tmp_path / "provider.json",
        "local_budget_path": tmp_path / "budget.json",
    }


def response(left="99"):
    result = Mock()
    result.status_code = 200
    result.headers = {"api-credits-left": left}
    return result


def execute(tmp_path, callback, approved=True):
    return execute_bootstrap(
        request_callback=callback,
        approval_id="approval-001",
        explicitly_approved=approved,
        now=NOW,
        **paths(tmp_path),
    )


def test_approved_bootstrap_refreshes_state(tmp_path):
    callback = Mock(return_value=response())

    result = execute(tmp_path, callback)

    assert result.request_executed is True
    assert result.credits_refreshed is True
    assert result.credits_left == 99
    callback.assert_called_once()

    state = load_credit_state(
        path=paths(tmp_path)["provider_state_path"],
        now=NOW,
    )
    assert state.credits_left == 99


def test_approval_required(tmp_path):
    callback = Mock()

    with pytest.raises(BootstrapNotPermitted):
        execute(tmp_path, callback, approved=False)

    callback.assert_not_called()


def test_bootstrap_cannot_be_repeated(tmp_path):
    execute(tmp_path, Mock(return_value=response()))

    callback = Mock()

    with pytest.raises(BootstrapNotPermitted):
        execute(tmp_path, callback)

    callback.assert_not_called()


def test_existing_low_credits_cannot_be_bypassed(tmp_path):
    provider_path = paths(tmp_path)["provider_state_path"]

    save_credit_state(
        CreditSnapshot(
            credits_used=1,
            credits_left=5,
            low_credits=True,
            information_available=True,
        ),
        path=provider_path,
        now=NOW,
    )

    callback = Mock()

    with pytest.raises(BootstrapNotPermitted):
        execute(tmp_path, callback)

    callback.assert_not_called()


def test_local_budget_failure_prevents_http(tmp_path):
    callback = Mock()

    with patch(
        "market_data.bootstrap_request_coordinator.reserve_request",
        side_effect=RuntimeError("Budget unavailable"),
    ):
        with pytest.raises(RuntimeError, match="Budget unavailable"):
            execute(tmp_path, callback)

    callback.assert_not_called()


def test_missing_credit_headers_not_treated_as_successful_refresh(tmp_path):
    callback = Mock(return_value=response_without_headers())

    result = execute(tmp_path, callback)

    assert result.request_executed is True
    assert result.credits_refreshed is False
    assert result.credits_left is None


def response_without_headers():
    result = Mock()
    result.status_code = 200
    result.headers = {}
    return result


@pytest.mark.parametrize("status", [400, 401, 403, 429, 500, 503])
def test_http_errors_not_treated_as_success(tmp_path, status):
    result = response()
    result.status_code = status

    callback = Mock(return_value=result)

    with pytest.raises(
        BootstrapNotPermitted,
        match="HTTP response not successful",
    ):
        execute(tmp_path, callback)

    callback.assert_called_once()

    assert not paths(tmp_path)["provider_state_path"].exists()
    assert paths(tmp_path)["approval_path"].exists()


def test_missing_http_status_blocked(tmp_path):
    result = response()
    del result.status_code

    with pytest.raises(BootstrapNotPermitted):
        execute(tmp_path, Mock(return_value=result))


def test_invalid_http_status_blocked(tmp_path):
    result = response()
    result.status_code = "200"

    with pytest.raises(BootstrapNotPermitted):
        execute(tmp_path, Mock(return_value=result))
