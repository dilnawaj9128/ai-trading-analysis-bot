from datetime import datetime, timezone

import pytest

from market_data.manual_credit_refresh import (
    ManualRefreshBlocked,
    manual_credit_refresh,
)
from market_data.manual_refresh_preparation import (
    prepare_manual_refresh,
)


NOW = datetime(2026, 11, 18, 12, 0, tzinfo=timezone.utc)


def arguments(tmp_path):
    return {
        "approval_id": "stage22b-test",
        "approval_path": tmp_path / "approval.json",
        "lifecycle_path": tmp_path / "lifecycle.json",
        "explicitly_approved": True,
        "now": NOW,
    }


def test_approval_and_lifecycle_are_bound(tmp_path):
    args = arguments(tmp_path)

    result = prepare_manual_refresh(**args)

    assert result["status"] == "CLAIMED"
    assert result["offline_only"] is True
    assert result["http_authorized"] is False
    assert result["settlement_authorized"] is False

    assert args["approval_path"].exists()
    assert args["lifecycle_path"].exists()

    marker = tmp_path / "approval.json.consumed"
    assert marker.exists()


def test_duplicate_approval_cannot_be_reused(tmp_path):
    args = arguments(tmp_path)
    prepare_manual_refresh(**args)

    with pytest.raises(Exception):
        prepare_manual_refresh(**args)


def test_missing_approval_changes_nothing(tmp_path):
    args = arguments(tmp_path)
    args["explicitly_approved"] = False

    with pytest.raises(ValueError, match="Explicit approval"):
        prepare_manual_refresh(**args)

    assert not list(tmp_path.iterdir())


def test_production_budget_path_blocks_callback(tmp_path):
    from market_data.twelve_data_client import STATE_PATH

    calls = []

    def callback():
        calls.append(True)
        raise AssertionError("HTTP callback must not run")

    with pytest.raises(
        ManualRefreshBlocked,
        match="Production refresh authorization",
    ):
        manual_credit_refresh(
            request_callback=callback,
            approval_id="stage22b-test",
            explicitly_approved=True,
            provider_path=tmp_path / "provider.json",
            budget_path=STATE_PATH,
            now=NOW,
        )

    assert calls == []
    assert not list(tmp_path.iterdir())
