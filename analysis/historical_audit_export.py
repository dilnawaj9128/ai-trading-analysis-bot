"""Reproducible, offline-only historical signal audit exports.

DataFrame must come from separately validated/audited candles. This module
performs no file writes or network requests and never authorizes trading.
"""
import json

import pandas as pd

from analysis.historical_signal_audit import (
    build_signal_audit_record,
    verify_signal_audit_record,
)


EXPORT_COLUMNS = (
    "observation_utc", "evaluation_utc", "selected_index",
    "strategy_signal", "historical_outcome", "comparison",
    "dataset_integrity", "provider_feed", "broker_prices",
    "record_sha256", "reasons",
)


def build_audit_exports(frame, *, dataset_audit, start_index=59, step=15):
    """Return independently checkable records plus CSV and JSON bytes.

    Fail closed if any observation cannot be validated; do not silently skip.
    Non-overlapping 15-minute windows; no look-ahead in strategy inputs.
    """
    if not isinstance(frame, pd.DataFrame):
        raise ValueError("Historical candles must be a DataFrame")
    if not isinstance(dataset_audit, dict) or dataset_audit.get("status") != "PASS":
        raise ValueError("Dataset integrity audit must PASS")
    if type(start_index) is not int or start_index < 59:
        raise ValueError("start_index must be an integer >= 59")
    if type(step) is not int or step < 15:
        raise ValueError("step must be an integer >= 15")
    if len(frame) < start_index + 16:
        raise ValueError("Not enough completed candles for an audit window")

    records = []
    for index in range(start_index, len(frame) - 15, step):
        record = build_signal_audit_record(
            frame, selected_index=index, dataset_audit=dataset_audit
        )
        if not verify_signal_audit_record(record):
            raise ValueError("Audit record checksum verification failed")
        records.append(record)

    if not records:
        raise ValueError("No complete 15-minute observation windows")

    table = pd.DataFrame(records)
    display = table.loc[:, list(EXPORT_COLUMNS)].copy()
    # CSV is flat: store reasons as a JSON array string, not a Python repr.
    display["reasons"] = display["reasons"].map(
        lambda reasons: json.dumps(reasons, ensure_ascii=False, allow_nan=False)
    )
    json_bytes = json.dumps(
        records, ensure_ascii=False, indent=2, allow_nan=False
    ).encode("utf-8")
    csv_bytes = display.to_csv(index=False).encode("utf-8")
    return {
        "records": records,
        "table": display,
        "csv_bytes": csv_bytes,
        "json_bytes": json_bytes,
        "record_count": len(records),
    }
