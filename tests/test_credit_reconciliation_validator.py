import pytest

from market_data.credit_reconciliation_validator import (
    validate_reconciliation_candidate,
)

ATTEMPT = {
    "attempt_id": "a" * 32,
    "attempted_at": "2026-11-18T10:00:00+00:00",
    "status": "CLAIMED",
}

EVIDENCE = {
    "attempt_id": "a" * 32,
    "observed_at": "2026-11-18T10:01:00+00:00",
    "credits_left": 7,
}


def test_candidate_is_not_authorized_for_completion():
    result = validate_reconciliation_candidate(
        ATTEMPT, EVIDENCE
    )

    assert result["structurally_valid"] is True
    assert result["verified_provider_provenance"] is False
    assert result["completion_authorized"] is False


def test_wrong_attempt_id_rejected():
    with pytest.raises(ValueError):
        validate_reconciliation_candidate(
            ATTEMPT,
            {**EVIDENCE, "attempt_id": "b" * 32},
        )


def test_older_evidence_rejected():
    with pytest.raises(ValueError):
        validate_reconciliation_candidate(
            ATTEMPT,
            {
                **EVIDENCE,
                "observed_at": "2026-11-18T09:00:00Z",
            },
        )


def test_invalid_credit_value_rejected():
    with pytest.raises(ValueError):
        validate_reconciliation_candidate(
            ATTEMPT,
            {**EVIDENCE, "credits_left": -1},
        )


def test_uncertain_attempt_rejected():
    with pytest.raises(ValueError):
        validate_reconciliation_candidate(
            {**ATTEMPT, "status": "UNCERTAIN"},
            EVIDENCE,
        )
