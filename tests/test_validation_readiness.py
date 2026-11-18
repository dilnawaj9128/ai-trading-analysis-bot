import pytest

from analysis.validation_readiness import (
    check_validation_readiness,
)


def audit(status="PASS"):
    return {
        "status": status,
        "metrics": {},
        "warnings": [],
    }


def test_small_dataset_blocked():
    result = check_validation_readiness(
        audit(), training_rows=120
    )
    assert result["status"] == "BLOCKED"
    assert result["minimum_rows"] == 716


def test_enough_rows_do_not_bypass_provenance():
    result = check_validation_readiness(
        audit(), training_rows=2000
    )
    assert result["status"] == "BLOCKED"
    assert result["accuracy_available"] is False


def test_failed_integrity_blocks():
    result = check_validation_readiness(
        audit("FAIL"), training_rows=2000
    )
    assert any(
        "integrity" in reason.lower()
        for reason in result["blockers"]
    )


def test_negative_rows_rejected():
    with pytest.raises(ValueError):
        check_validation_readiness(
            audit(), training_rows=-1
        )


def test_boolean_rows_rejected():
    with pytest.raises(ValueError):
        check_validation_readiness(
            audit(), training_rows=True
        )


def test_invalid_window_settings_rejected():
    with pytest.raises(ValueError):
        check_validation_readiness(
            audit(),
            training_rows=2000,
            min_train=50,
        )
