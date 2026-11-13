from datetime import datetime, timezone

import pytest

from market_data.bootstrap_authorization import (
    BootstrapApprovalRequired,
    BootstrapApprovalAlreadyUsed,
    claim_bootstrap_approval,
)


NOW = datetime(2026, 11, 13, 12, 0, tzinfo=timezone.utc)


def claim(tmp_path, approval_id="approval-001", approved=True):
    return claim_bootstrap_approval(
        approval_id=approval_id,
        explicitly_approved=approved,
        path=tmp_path / "claim.json",
        now=NOW,
    )


def test_first_approved_claim(tmp_path):
    result = claim(tmp_path)

    assert result["approval_id"] == "approval-001"
    assert result["status"] == "claimed"


def test_same_approval_cannot_be_reused(tmp_path):
    claim(tmp_path)

    with pytest.raises(BootstrapApprovalAlreadyUsed):
        claim(tmp_path)


def test_different_approval_cannot_bypass_existing_claim(tmp_path):
    claim(tmp_path)

    with pytest.raises(BootstrapApprovalAlreadyUsed):
        claim(tmp_path, approval_id="approval-002")


def test_explicit_approval_required(tmp_path):
    with pytest.raises(BootstrapApprovalRequired):
        claim(tmp_path, approved=False)

    assert not (tmp_path / "claim.json").exists()


def test_claim_survives_restart(tmp_path):
    claim(tmp_path)

    with pytest.raises(BootstrapApprovalAlreadyUsed):
        claim(tmp_path)


@pytest.mark.parametrize("approval_id", ["", "   ", None, 123])
def test_invalid_approval_id(tmp_path, approval_id):
    with pytest.raises(ValueError):
        claim(tmp_path, approval_id=approval_id)


@pytest.mark.parametrize("approved", [1, None, "yes"])
def test_invalid_approval_flag(tmp_path, approved):
    with pytest.raises(ValueError):
        claim(tmp_path, approved=approved)


def test_naive_datetime_rejected(tmp_path):
    with pytest.raises(ValueError):
        claim_bootstrap_approval(
            approval_id="approval-001",
            explicitly_approved=True,
            path=tmp_path / "claim.json",
            now=datetime(2026, 11, 13, 12, 0),
        )
