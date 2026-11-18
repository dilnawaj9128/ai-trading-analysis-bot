from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from market_data.manual_credit_refresh import (
    ManualRefreshBlocked,
    manual_credit_refresh,
)


NOW = datetime(2026, 11, 18, 12, 0, tzinfo=timezone.utc)


def setup(tmp_path, callback, approved=True):
    return dict(
        request_callback=callback,
        approval_id="manual-test-approval",
        explicitly_approved=approved,
        provider_path=tmp_path / "provider.json",
        budget_path=tmp_path / "budget.json",
        now=NOW,
    )


def good_response():
    return SimpleNamespace(
        status_code=200,
        json=lambda: {
            "status": "ok",
            "values": [{"datetime": "2026-11-18 11:59:00"}],
        },
        headers={
            "api-credits-used": "1",
            "api-credits-left": "7",
        },
    )


def test_no_approval_no_request(tmp_path):
    called = []

    def callback():
        called.append(True)
        return good_response()

    with pytest.raises(ManualRefreshBlocked):
        manual_credit_refresh(
            **setup(tmp_path, callback, approved=False)
        )

    assert called == []
    assert not list(tmp_path.iterdir())


def test_successful_single_refresh(tmp_path):
    result = manual_credit_refresh(
        **setup(tmp_path, good_response)
    )

    assert result["status"] == "SNAPSHOT_REFRESHED"
    assert result["credits_left"] == 7
    assert result["settlement_authorized"] is False


def test_duplicate_refresh_blocked(tmp_path):
    arguments = setup(tmp_path, good_response)

    manual_credit_refresh(**arguments)

    with pytest.raises(
        ManualRefreshBlocked,
        match="already attempted",
    ):
        manual_credit_refresh(**arguments)


def test_invalid_response_stays_uncertain(tmp_path):
    response = lambda: SimpleNamespace(
        status_code=200,
        json=lambda: {"status": "error"},
        headers={},
    )

    result = manual_credit_refresh(
        **setup(tmp_path, response)
    )

    assert result["status"] == "UNCERTAIN"
    assert result["retry_allowed"] is False

    assert (
        tmp_path / "provider.json.manual_refresh_claim.json"
    ).exists()

    assert not (tmp_path / "provider.json").exists()
