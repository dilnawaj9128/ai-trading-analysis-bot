from datetime import datetime, timezone

import pytest

from market_data.credit_refresh_approval import (
    claim_credit_refresh_approval,
)
from market_data.credit_refresh_coordinator import (
    prepare_offline_refresh,
    CreditRefreshBindingError,
)


NOW = datetime(2026, 11, 18, 12, 0, tzinfo=timezone.utc)


def test_missing_approval_blocks(tmp_path):
    with pytest.raises(CreditRefreshBindingError):
        prepare_offline_refresh(
            approval_path=tmp_path / "approval.json",
            lifecycle_path=tmp_path / "lifecycle.json",
            approval_id="approved-1",
            now=NOW,
        )


def test_valid_approval_prepares_lifecycle(tmp_path):
    approval_path = tmp_path / "approval.json"
    lifecycle_path = tmp_path / "lifecycle.json"

    claim_credit_refresh_approval(
        approval_id="approved-1",
        explicitly_approved=True,
        path=approval_path,
        now=NOW,
    )

    result = prepare_offline_refresh(
        approval_path=approval_path,
        lifecycle_path=lifecycle_path,
        approval_id="approved-1",
        now=NOW,
    )

    assert result["status"] == "CLAIMED"
    assert result["offline_only"] is True


def test_wrong_approval_id_blocks(tmp_path):
    approval_path = tmp_path / "approval.json"

    claim_credit_refresh_approval(
        approval_id="approved-1",
        explicitly_approved=True,
        path=approval_path,
        now=NOW,
    )

    with pytest.raises(CreditRefreshBindingError):
        prepare_offline_refresh(
            approval_path=approval_path,
            lifecycle_path=tmp_path / "lifecycle.json",
            approval_id="different-approval",
            now=NOW,
        )


def test_corrupt_approval_blocks(tmp_path):
    approval_path = tmp_path / "approval.json"
    approval_path.write_text("{broken")

    with pytest.raises(CreditRefreshBindingError):
        prepare_offline_refresh(
            approval_path=approval_path,
            lifecycle_path=tmp_path / "lifecycle.json",
            approval_id="approved-1",
            now=NOW,
        )


def test_duplicate_preparation_blocks(tmp_path):
    approval_path = tmp_path / "approval.json"
    lifecycle_path = tmp_path / "lifecycle.json"

    claim_credit_refresh_approval(
        approval_id="approved-1",
        explicitly_approved=True,
        path=approval_path,
        now=NOW,
    )

    kwargs = {
        "approval_path": approval_path,
        "lifecycle_path": lifecycle_path,
        "approval_id": "approved-1",
        "now": NOW,
    }

    prepare_offline_refresh(**kwargs)

    with pytest.raises(RuntimeError):
        prepare_offline_refresh(**kwargs)
