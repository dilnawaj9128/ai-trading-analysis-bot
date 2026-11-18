import copy

import pytest

from market_data.refresh_request_binding import (
    validate_refresh_request_binding,
)


ATTEMPT_ID = "a" * 32
REQUEST_ID = "b" * 32


def evidence():
    return {
        "attempt": {
            "attempt_id": ATTEMPT_ID,
            "attempted_at": "2026-11-18T10:00:00+00:00",
            "status": "CLAIMED",
        },
        "approval_id": "approved-once",
        "request_id": REQUEST_ID,
        "reservation": {
            "status": "PENDING",
            "credits": 1,
            "authorized_at": "2026-11-18T10:01:00+00:00",
        },
        "journal_transaction": {
            "status": "FINALIZED",
            "credits": 1,
            "authorized_at": "2026-11-18T10:01:00+00:00",
        },
    }


def test_valid_structure_does_not_authorize_settlement():
    result = validate_refresh_request_binding(**evidence())

    assert result["structurally_valid"] is True
    assert result["trusted_response_verified"] is False
    assert result["settlement_authorized"] is False
    assert result["completion_authorized"] is False


def test_invalid_request_id_rejected():
    item = evidence()
    item["request_id"] = "invalid"

    with pytest.raises(ValueError, match="Invalid request ID"):
        validate_refresh_request_binding(**item)


def test_credit_mismatch_rejected():
    item = evidence()
    item["journal_transaction"]["credits"] = 2

    with pytest.raises(ValueError, match="Credit amount mismatch"):
        validate_refresh_request_binding(**item)


def test_non_pending_reservation_rejected():
    item = evidence()
    item["reservation"]["status"] = "UNCERTAIN"

    with pytest.raises(ValueError, match="PENDING"):
        validate_refresh_request_binding(**item)


def test_request_before_attempt_rejected():
    item = evidence()
    item["reservation"]["authorized_at"] = (
        "2026-11-18T09:59:00+00:00"
    )
    item["journal_transaction"]["authorized_at"] = (
        "2026-11-18T09:59:00+00:00"
    )

    with pytest.raises(ValueError, match="predates"):
        validate_refresh_request_binding(**item)


def test_unfinalized_journal_rejected():
    item = evidence()
    item["journal_transaction"]["status"] = "INTENT"

    with pytest.raises(ValueError, match="FINALIZED"):
        validate_refresh_request_binding(**item)
