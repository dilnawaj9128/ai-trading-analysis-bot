import pytest

from market_data.request_response_evidence import (
    validate_response_evidence,
)

REQUEST_ID = "a" * 32
TIME = "2026-11-18T10:00:00+00:00"


def evidence():
    return {
        "request_id": REQUEST_ID,
        "reservation": {
            "credits": 1,
            "status": "PENDING",
            "authorized_at": TIME,
        },
        "journal_transaction": {
            "credits": 1,
            "status": "FINALIZED",
            "authorized_at": TIME,
        },
        "response_status": 200,
        "response_headers": {
            "api-credits-used": "1",
            "api-credits-left": "7",
        },
    }


def test_valid_response_remains_untrusted():
    result = validate_response_evidence(**evidence())
    assert result["structurally_valid"] is True
    assert result["trusted_provider_provenance"] is False
    assert result["settlement_authorized"] is False
    assert result["completion_authorized"] is False


def test_invalid_http_status():
    item = evidence()
    item["response_status"] = 429

    with pytest.raises(ValueError, match="unsuccessful"):
        validate_response_evidence(**item)


def test_missing_credit_header():
    item = evidence()
    del item["response_headers"]["api-credits-left"]

    with pytest.raises(ValueError, match="credit headers"):
        validate_response_evidence(**item)


def test_invalid_request_id():
    item = evidence()
    item["request_id"] = "bad"

    with pytest.raises(ValueError, match="Invalid request ID"):
        validate_response_evidence(**item)


def test_credit_mismatch():
    item = evidence()
    item["reservation"]["credits"] = 2

    with pytest.raises(ValueError, match="Credits mismatch"):
        validate_response_evidence(**item)


def test_uncertain_reservation_rejected():
    item = evidence()
    item["reservation"]["status"] = "UNCERTAIN"

    with pytest.raises(ValueError, match="PENDING"):
        validate_response_evidence(**item)


def test_negative_credits_rejected():
    item = evidence()
    item["response_headers"]["api-credits-left"] = "-1"

    with pytest.raises(ValueError, match="Negative"):
        validate_response_evidence(**item)
