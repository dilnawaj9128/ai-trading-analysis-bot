"""Offline, deterministic historical signal audit records.

No HTTP, broker access, trading execution or automatic file writes.
SHA-256 detects record changes; it does not prove source authenticity.
"""

import hashlib
import json

from analysis.historical_signal_comparison import (
    evaluate_historical_signal,
)
from analysis.provenance_audit import summarize_provenance


def _digest(payload):
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def build_signal_audit_record(
    frame,
    *,
    selected_index,
    dataset_audit,
):
    """Build one research record without changing source data."""

    provenance = summarize_provenance(dataset_audit)

    if provenance["dataset_integrity"] != "PASS":
        raise ValueError(
            "Dataset integrity must PASS before audit generation"
        )

    comparison = evaluate_historical_signal(
        frame,
        selected_index=selected_index,
    )

    record = {
        "schema_version": 1,
        "observation_utc": comparison["observation_utc"],
        "evaluation_utc": comparison["evaluation_utc"],
        "selected_index": selected_index,
        "expiry_minutes": comparison["expiry_minutes"],
        "candles_used": comparison["candles_used_for_signal"],
        "strategy_signal": comparison["signal"],
        "historical_outcome": comparison["historical_outcome"],
        "comparison": comparison["comparison"],
        "reasons": list(comparison["reasons"]),
        "dataset_integrity": provenance["dataset_integrity"],
        "provider_feed": provenance["provider_feed_verification"],
        "broker_prices": provenance["broker_price_verification"],
        "directional_evaluation_allowed": provenance[
            "directional_evaluation_allowed"
        ],
        "analysis_only": True,
        "execution_enabled": False,
        "prediction_accuracy_available": False,
    }

    return {
        **record,
        "record_sha256": _digest(record),
    }


def verify_signal_audit_record(record):
    """Check a record against its stored checksum."""

    if not isinstance(record, dict):
        return False

    expected = record.get("record_sha256")

    if not isinstance(expected, str) or len(expected) != 64:
        return False

    payload = {
        key: value
        for key, value in record.items()
        if key != "record_sha256"
    }

    try:
        return _digest(payload) == expected
    except (TypeError, ValueError):
        return False
