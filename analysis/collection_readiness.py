"""Offline data sufficiency estimates. No HTTP or quota reservations."""


def calculate_collection_readiness(
    *,
    raw_candles,
    eligible_rows,
    required_rows=716,
):
    values = (raw_candles, eligible_rows, required_rows)

    if any(type(value) is not int for value in values):
        raise ValueError("Integer counts required")

    if (
        raw_candles < 0
        or eligible_rows < 0
        or required_rows < 1
        or eligible_rows > raw_candles
    ):
        raise ValueError("Invalid dataset counts")

    missing = max(0, required_rows - eligible_rows)
    excluded = raw_candles - eligible_rows

    # Estimate assumes future candles form one uninterrupted
    # sequence with similar feature warmup behavior.
    estimated_total_raw = max(
        raw_candles,
        required_rows + excluded,
    )

    return {
        "raw_candles": raw_candles,
        "eligible_rows": eligible_rows,
        "required_rows": required_rows,
        "missing_eligible_rows": missing,
        "estimated_total_raw_candles": estimated_total_raw,
        "estimated_additional_raw_candles": max(
            0, estimated_total_raw - raw_candles
        ),
        "sufficient_rows": eligible_rows >= required_rows,
        "estimate_only": True,
        "collection_authorized": False,
        "analysis_only": True,
    }
