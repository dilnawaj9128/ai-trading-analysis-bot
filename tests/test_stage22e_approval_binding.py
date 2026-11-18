import json
from datetime import datetime, timezone

import pytest

from market_data.manual_refresh_preparation import (
    prepare_manual_refresh,
    verify_prepared_manual_refresh,
)


NOW = datetime(2026, 11, 18, 12, 0, tzinfo=timezone.utc)


def prepare(tmp_path):
    approval = tmp_path / "approval.json"
    lifecycle = tmp_path / "lifecycle.json"

    prepare_manual_refresh(
        approval_id="stage22e",
        approval_path=approval,
        lifecycle_path=lifecycle,
        explicitly_approved=True,
        now=NOW,
    )

    return approval, lifecycle


def test_persisted_binding_is_valid(tmp_path):
    approval, lifecycle = prepare(tmp_path)

    result = verify_prepared_manual_refresh(
        approval_path=approval,
        lifecycle_path=lifecycle,
        approval_id="stage22e",
    )

    assert result["verified_local_binding"] is True
    assert result["http_authorized"] is False
    assert result["settlement_authorized"] is False


def test_wrong_approval_id_rejected(tmp_path):
    approval, lifecycle = prepare(tmp_path)

    with pytest.raises(ValueError, match="binding mismatch"):
        verify_prepared_manual_refresh(
            approval_path=approval,
            lifecycle_path=lifecycle,
            approval_id="wrong-approval",
        )


def test_modified_consumption_marker_rejected(tmp_path):
    approval, lifecycle = prepare(tmp_path)

    marker = tmp_path / "approval.json.consumed"
    data = json.loads(marker.read_text())
    data["approval_claim_id"] = "f" * 32
    marker.write_text(json.dumps(data))

    with pytest.raises(ValueError, match="binding mismatch"):
        verify_prepared_manual_refresh(
            approval_path=approval,
            lifecycle_path=lifecycle,
            approval_id="stage22e",
        )


def test_missing_marker_rejected(tmp_path):
    approval, lifecycle = prepare(tmp_path)

    (tmp_path / "approval.json.consumed").unlink()

    with pytest.raises(ValueError, match="unavailable"):
        verify_prepared_manual_refresh(
            approval_path=approval,
            lifecycle_path=lifecycle,
            approval_id="stage22e",
        )
