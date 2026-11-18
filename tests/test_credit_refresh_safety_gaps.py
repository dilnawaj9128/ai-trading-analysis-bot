import json
from datetime import datetime, timezone
from unittest.mock import patch

import pytest

from market_data.credit_refresh_approval import (
    claim_credit_refresh_approval,
)
from market_data.credit_refresh_coordinator import (
    prepare_offline_refresh,
)
from market_data.credit_refresh_store import (
    claim_refresh_attempt,
    transition_refresh_attempt,
)

NOW = datetime(2026, 11, 18, 12, 0, tzinfo=timezone.utc)


def test_unverified_completion_must_be_rejected(tmp_path):
    path = tmp_path / "lifecycle.json"
    from market_data.credit_refresh_store import _claim_refresh_attempt_internal
    attempt = _claim_refresh_attempt_internal(path=path, now=NOW)

    with pytest.raises((ValueError, RuntimeError)):
        transition_refresh_attempt(
            path=path,
            attempt_id=attempt["attempt_id"],
            status="COMPLETED",
        )


def test_crash_before_lifecycle_claim_must_block_reuse(tmp_path):
    approval_path = tmp_path / "approval.json"
    lifecycle_path = tmp_path / "lifecycle.json"

    claim_credit_refresh_approval(
        approval_id="approval-1",
        explicitly_approved=True,
        path=approval_path,
        now=NOW,
    )

    with patch(
        "market_data.credit_refresh_coordinator._claim_refresh_attempt_internal",
        side_effect=RuntimeError("simulated crash"),
    ):
        with pytest.raises(RuntimeError):
            prepare_offline_refresh(
                approval_path=approval_path,
                lifecycle_path=lifecycle_path,
                approval_id="approval-1",
                now=NOW,
            )

    # Reusing an approval after a failed preparation must
    # not silently create a fresh attempt.
    with pytest.raises(RuntimeError):
        prepare_offline_refresh(
            approval_path=approval_path,
            lifecycle_path=lifecycle_path,
            approval_id="approval-1",
            now=NOW,
        )


def test_lifecycle_claim_requires_approval_binding(tmp_path):
    path = tmp_path / "lifecycle.json"

    # A production-bound lifecycle claim must not be
    # creatable without validated approval evidence.
    with pytest.raises((ValueError, RuntimeError)):
        claim_refresh_attempt(path=path, now=NOW)
