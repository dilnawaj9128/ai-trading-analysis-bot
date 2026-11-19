"""Stage 51B: append-only, source-linked forward observations.

No API requests, no directional signal authorization, no orders.
The saved CSV is NOT assumed to have verified provider provenance.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from research.stage51_forward_recorder import (
    PROBE,
    CSV,
    OUT,
    build_record,
    canonical,
    save_record,
    verify_record,
)

SCHEMA = 2


def file_hash(path):
    """Return source SHA256 without exposing file contents."""
    path = Path(path)

    if path.is_symlink() or not path.is_file():
        return None

    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_observation(*, now=None, probe_path=PROBE, csv_path=CSV):
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError("UTC-aware clock required")

    now = now.astimezone(timezone.utc)

    # Reuse all existing safety and candle-quality checks.
    record = build_record(
        now=now,
        probe_path=probe_path,
        csv_path=csv_path,
    )

    csv_sha = file_hash(csv_path)
    probe_sha = file_hash(probe_path)

    if csv_sha is None:
        record["reasons"] = sorted(set(
            record["reasons"] + ["CSV_SOURCE_UNAVAILABLE"]
        ))

    # Stable identity for the same source snapshots.
    identity = {
        "stage": "51B",
        "schema": SCHEMA,
        "symbol": record["symbol"],
        "candle": record["latest_candle_open_utc"],
        "csv_sha256": csv_sha,
        "probe_sha256": probe_sha,
    }

    observation_id = hashlib.sha256(
        canonical(identity)
    ).hexdigest()

    record.update({
        "schema_version": SCHEMA,
        "decision_id": observation_id,
        "observation_type": "FORWARD_READINESS_OBSERVATION",
        "csv_sha256": csv_sha,
        "probe_journal_sha256": probe_sha,
        "provider_origin_verified": False,
        "broker_parity_verified": False,
        "signal": "NO TRADE",
        "authorization": "BLOCKED",
        "prediction_generated": False,
        "forward_accuracy_proven": False,
        "execution_enabled": False,
    })

    return record


def record_observation(*, now=None, probe_path=PROBE,
                       csv_path=CSV, output_dir=OUT):
    record = build_observation(
        now=now,
        probe_path=probe_path,
        csv_path=csv_path,
    )

    target = Path(output_dir) / (
        record["decision_id"] + ".json"
    )

    try:
        path = save_record(record, output_dir=output_dir)
        created = True
    except FileExistsError:
        path = target
        created = False

    if not verify_record(path):
        raise ValueError("Existing observation checksum mismatch")

    saved = json.loads(
        path.read_text(encoding="utf-8")
    )["record"]

    if (
        saved.get("decision_id") != record["decision_id"]
        or saved.get("csv_sha256") != record["csv_sha256"]
        or saved.get("probe_journal_sha256")
        != record["probe_journal_sha256"]
        or saved.get("signal") != "NO TRADE"
        or saved.get("authorization") != "BLOCKED"
        or saved.get("prediction_generated") is not False
    ):
        raise ValueError("Observation identity or safety mismatch")

    return saved, path, created
