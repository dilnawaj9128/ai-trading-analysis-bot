from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

import pytest

from market_data.credit_refresh_approval import (
    claim_credit_refresh_approval,
    CreditRefreshApprovalRequired,
    CreditRefreshApprovalAlreadyUsed,
)


def claim(path, approved=True, approval_id="test-approval"):
    return claim_credit_refresh_approval(
        approval_id=approval_id,
        explicitly_approved=approved,
        path=path,
        now=datetime(2026, 11, 18, tzinfo=timezone.utc),
    )


def test_explicit_approval_required(tmp_path):
    path = tmp_path / "claim.json"

    with pytest.raises(CreditRefreshApprovalRequired):
        claim(path, approved=False)

    assert not path.exists()


def test_single_use_claim(tmp_path):
    path = tmp_path / "claim.json"

    result = claim(path)
    assert result["status"] == "CLAIMED_OFFLINE"

    with pytest.raises(CreditRefreshApprovalAlreadyUsed):
        claim(path)


def test_claim_persists(tmp_path):
    path = tmp_path / "claim.json"

    claim(path)
    assert path.exists()


def test_invalid_approval_id(tmp_path):
    with pytest.raises(ValueError):
        claim(tmp_path / "claim.json", approval_id="")


def test_invalid_approval_flag(tmp_path):
    with pytest.raises(ValueError):
        claim_credit_refresh_approval(
            approval_id="test",
            explicitly_approved=1,
            path=tmp_path / "claim.json",
        )


def test_concurrent_claim_only_one_succeeds(tmp_path):
    path = tmp_path / "claim.json"

    def attempt(_):
        try:
            claim(path)
            return "SUCCESS"
        except CreditRefreshApprovalAlreadyUsed:
            return "BLOCKED"

    with ThreadPoolExecutor(max_workers=8) as executor:
        results = list(executor.map(attempt, range(8)))

    assert results.count("SUCCESS") == 1
    assert results.count("BLOCKED") == 7
