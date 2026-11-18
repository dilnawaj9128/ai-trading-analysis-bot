"""Conservative, offline-only provenance status reporting."""


def summarize_provenance(audit):
    if not isinstance(audit, dict):
        raise ValueError("Dataset audit dictionary required")

    integrity = audit.get("status")

    if integrity not in ("PASS", "FAIL"):
        raise ValueError("Dataset audit status unavailable")

    metrics = audit.get("metrics", {})
    if not isinstance(metrics, dict):
        raise ValueError("Invalid audit metrics")

    warnings = audit.get("warnings", [])
    if not isinstance(warnings, list):
        raise ValueError("Invalid audit warnings")

    # A structural integrity audit does not independently
    # establish live/delayed feed authenticity or broker parity.
    return {
        "dataset_integrity": integrity,
        "provider_feed_verification": "UNVERIFIED",
        "broker_price_verification": "UNVERIFIED",
        "directional_evaluation_allowed": False,
        "reasons": [
            "Dataset integrity and market-feed provenance are separate checks.",
            "Independent provider feed-mode evidence is not established.",
            "Broker candle timestamps and prices have not been independently matched.",
        ],
        "analysis_only": True,
    }
