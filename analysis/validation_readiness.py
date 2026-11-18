"""Offline readiness checks before out-of-sample evaluation."""

from analysis.provenance_audit import summarize_provenance


def check_validation_readiness(
    dataset_audit,
    *,
    training_rows,
    min_train=500,
    test_size=200,
    embargo_rows=16,
):
    settings = (training_rows, min_train, test_size, embargo_rows)

    if any(type(value) is not int for value in settings):
        raise ValueError("Integer settings required")

    if (
        training_rows < 0
        or min_train < 100
        or test_size < 30
        or embargo_rows < 16
    ):
        raise ValueError("Invalid validation settings")

    provenance = summarize_provenance(dataset_audit)
    required_rows = min_train + test_size + embargo_rows

    blockers = []

    if provenance["dataset_integrity"] != "PASS":
        blockers.append("Dataset integrity audit did not pass")

    if training_rows < required_rows:
        blockers.append(
            f"Insufficient training rows: {training_rows} "
            f"available, at least {required_rows} required"
        )

    if provenance["provider_feed_verification"] != "VERIFIED":
        blockers.append("Provider feed verification is missing")

    if provenance["broker_price_verification"] != "VERIFIED":
        blockers.append("Broker price verification is missing")

    return {
        "status": "BLOCKED" if blockers else "READY",
        "training_rows": training_rows,
        "minimum_rows": required_rows,
        "blockers": blockers,
        "accuracy_available": False,
        "analysis_only": True,
    }
