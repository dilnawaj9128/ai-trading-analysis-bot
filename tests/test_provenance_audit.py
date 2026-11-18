import pytest

from analysis.provenance_audit import summarize_provenance


def test_integrity_pass_does_not_verify_feed():
    result = summarize_provenance({
        "status": "PASS",
        "metrics": {},
        "warnings": [],
    })

    assert result["dataset_integrity"] == "PASS"
    assert result["provider_feed_verification"] == "UNVERIFIED"
    assert result["directional_evaluation_allowed"] is False


def test_broker_not_verified_by_integrity():
    result = summarize_provenance({
        "status": "PASS",
        "metrics": {"broker_verified": True},
        "warnings": [],
    })

    assert result["broker_price_verification"] == "UNVERIFIED"


def test_failed_integrity_not_accepted():
    result = summarize_provenance({
        "status": "FAIL",
        "metrics": {},
        "warnings": [],
    })

    assert result["dataset_integrity"] == "FAIL"
    assert result["directional_evaluation_allowed"] is False


def test_invalid_audit_rejected():
    with pytest.raises(ValueError):
        summarize_provenance({"status": "UNKNOWN"})
