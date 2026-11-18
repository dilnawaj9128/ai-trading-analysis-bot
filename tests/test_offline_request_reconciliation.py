import pytest

from market_data.offline_request_reconciliation import (
    evaluate_offline_response,
)


REQUEST_ID = "a" * 32
TIMESTAMP = "2026-11-18T10:00:00+00:00"


def evidence():
    return {
        "request_id": REQUEST_ID,
        "journal": {
            "transactions": {
                REQUEST_ID: {
                    "status": "FINALIZED",
                    "credits": 1,
                    "authorized_at": TIMESTAMP,
                }
            }
        },
        "ledger": {
            "requests": {
                REQUEST_ID: {
                    "status": "PENDING",
                    "credits": 1,
                    "authorized_at": TIMESTAMP,
                }
            }
        },
        "response_status": 200,
        "response_headers": {
            "api-credits-used": "1",
            "api-credits-left": "7",
        },
    }


def test_valid_response_does_not_settle():
    result = evaluate_offline_response(**evidence())

    assert result["consistent"] is True
    assert result["response_structurally_valid"] is True
    assert result["settlement_authorized"] is False
    assert result["completion_authorized"] is False


def test_unknown_request_rejected():
    data = evidence()
    data["request_id"] = "b" * 32

    with pytest.raises(ValueError, match="missing"):
        evaluate_offline_response(**data)


def test_failed_http_rejected():
    data = evidence()
    data["response_status"] = 500

    with pytest.raises(ValueError, match="unsuccessful"):
        evaluate_offline_response(**data)


def test_mismatched_credits_rejected():
    data = evidence()
    data["ledger"]["requests"][REQUEST_ID]["credits"] = 2

    with pytest.raises(ValueError, match="credits mismatch"):
        evaluate_offline_response(**data)


def test_uncertain_request_rejected():
    data = evidence()
    data["ledger"]["requests"][REQUEST_ID]["status"] = "UNCERTAIN"

    with pytest.raises(ValueError, match="PENDING"):
        evaluate_offline_response(**data)
