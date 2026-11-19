"""Stage 51: fail-closed, offline forward-research evidence recorder.

No HTTP requests, broker integration, trade execution or directional
prediction authorization. One atomic, create-only JSON file per decision.
"""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from market_data.probe_cross_path_gate import check_probe_state
from research.stage29_backtest import load_candles

PROBE = Path("data/api_usage/approved_research_probe.json")
CSV = Path("data/real_market/latest_eurusd_completed.csv")
OUT = Path("data/research/stage51/decisions")


def canonical(value):
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def build_record(*, now=None, probe_path=PROBE, csv_path=CSV):
    now = now or datetime.now(timezone.utc)

    if now.tzinfo is None:
        raise ValueError("Timezone-aware clock required")

    now = now.astimezone(timezone.utc)
    reasons = []

    try:
        probe_status = check_probe_state(probe_path)
    except Exception:
        probe_status = "BLOCKED"
        reasons.append("UNRESOLVED_OR_INVALID_PROBE_EVIDENCE")

    if probe_status != "VERIFIED":
        reasons.append("PROVIDER_REQUEST_NOT_READY")

    latest = None
    candle_count = 0

    try:
        candles = load_candles(csv_path)
        candle_count = len(candles)

        if candles.timestamp.diff().iloc[1:].ne(
            timedelta(minutes=1)
        ).any():
            reasons.append("CANDLE_CONTINUITY_INVALID")

        if candle_count < 60:
            reasons.append("INSUFFICIENT_CANDLES")

        latest = candles.timestamp.iloc[-1].to_pydatetime()
        last_complete = latest + timedelta(minutes=1)
        age = (now - last_complete).total_seconds()

        if age < 0:
            reasons.append("CANDLE_NOT_COMPLETED")
        elif age > 180:
            reasons.append("MARKET_DATA_STALE")

    except (OSError, ValueError, TypeError, KeyError):
        reasons.append("SAVED_CANDLE_VALIDATION_FAILED")

    # Neither a verified probe nor a valid CSV independently establishes
    # authenticated provider provenance, feed mode or broker price parity.
    reasons.extend([
        "PROVIDER_PROVENANCE_UNVERIFIED",
        "FEED_MODE_UNVERIFIED",
        "BROKER_PRICE_PARITY_UNVERIFIED",
        "FORWARD_ACCURACY_NOT_ESTABLISHED",
    ])

    return {
        "schema_version": 1,
        "decision_id": uuid.uuid4().hex,
        "recorded_at_utc": now.isoformat(),
        "symbol": "EUR/USD",
        "timeframe": "1min",
        "expiry_minutes": 15,
        "probe_status": probe_status,
        "latest_candle_open_utc": (
            latest.isoformat() if latest is not None else None
        ),
        "candle_count": candle_count,
        "signal": "NO TRADE",
        "authorization": "BLOCKED",
        "reasons": sorted(set(reasons)),
        "source": "LOCAL_RESEARCH_EVIDENCE",
        "prediction_generated": False,
        "forward_accuracy_proven": False,
        "execution_enabled": False,
    }


def save_record(record, *, output_dir=OUT):
    """Create atomically; existing records are never overwritten."""
    directory = Path(output_dir)
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)

    body = canonical(record)
    envelope = {
        "record": record,
        "sha256": hashlib.sha256(body).hexdigest(),
    }

    target = directory / (record["decision_id"] + ".json")
    temporary = None

    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            dir=directory,
            prefix=".stage51_",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary = Path(handle.name)
            os.fchmod(handle.fileno(), 0o600)
            handle.write(canonical(envelope))
            handle.flush()
            os.fsync(handle.fileno())

        # Atomic create-only publication; never replace a record.
        os.link(temporary, target)

        directory_fd = os.open(directory, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)

        return target
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def verify_record(path):
    envelope = json.loads(Path(path).read_text(encoding="utf-8"))
    actual = hashlib.sha256(
        canonical(envelope["record"])
    ).hexdigest()
    return actual == envelope["sha256"]
