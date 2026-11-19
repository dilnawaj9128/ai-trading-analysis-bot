"""Stage 32 fail-closed, offline snapshot evaluation and forward journal.

No network, credentials, broker connection, or order execution. The source
verification flag MUST come from a trusted upstream verification workflow,
NOT from the presence of a CSV file alone. This module cannot prove provider
or broker parity and never claims profitable predictions.
"""
from __future__ import annotations

import json
import math
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

REQUIRED = ("timestamp", "Open", "High", "Low", "Close")
VALID_SIGNALS = {"UP", "DOWN", "NO TRADE"}


def _utc(value):
    stamp = pd.Timestamp(value)
    if stamp.tzinfo is None:
        raise ValueError("Explicit timezone required")
    return stamp.tz_convert("UTC")


def assess_snapshot(candles: pd.DataFrame, *, observed_at, symbol="EUR/USD",
                    timeframe="1min", source_verified=False, feed_mode="unknown",
                    max_age_seconds=180, min_candles=60):
    """Check a prospective signal using only completed, fresh, contiguous bars."""
    def blocked(reason, age=None):
        return {"signal": "NO TRADE", "status": "BLOCKED",
                "reason": reason, "age_seconds": age,
                "symbol": symbol, "timeframe": timeframe, "expiry_minutes": 15}

    try:
        now = _utc(observed_at)
        if symbol not in ("EUR/USD", "GBP/USD", "USD/JPY"):
            return blocked("Unsupported symbol")
        if timeframe != "1min":
            return blocked("Only completed 1min candles supported in Stage 32")
        if feed_mode not in ("live", "delayed") or source_verified is not True:
            return blocked("Feed mode or trusted provider provenance not verified")
        if type(max_age_seconds) not in (int, float) or not 0 <= max_age_seconds <= 180:
            return blocked("Invalid freshness policy")
        if not isinstance(candles, pd.DataFrame) or not set(REQUIRED).issubset(candles):
            return blocked("Missing candle fields")
        if len(candles) < min_candles or min_candles < 60:
            return blocked("Insufficient candles")
        data = candles.copy(deep=True)
        values = data["timestamp"].astype(str)
        if not values.str.contains(r"(?:Z|[+-]\\d{2}:\\d{2})$", regex=True).all():
            # In-memory timezone-aware Timestamp values also produce offsets.
            return blocked("Timestamps must include timezone offset")
        data["timestamp"] = pd.to_datetime(data["timestamp"], utc=True, errors="raise")
        if data["timestamp"].isna().any() or data["timestamp"].duplicated().any():
            return blocked("Missing or duplicate timestamps")
        if not data["timestamp"].is_monotonic_increasing:
            return blocked("Timestamps out of order")
        if ((data["timestamp"].dt.second != 0) |
                (data["timestamp"].dt.microsecond != 0)).any():
            return blocked("Candle timestamps not minute-aligned")
        for field in REQUIRED[1:]:
            data[field] = pd.to_numeric(data[field], errors="raise")
            if not data[field].map(lambda x: math.isfinite(x) and x > 0).all():
                return blocked("Invalid candle price")
        if not (data.High >= data[["Open", "Close", "Low"]].max(axis=1)).all():
            return blocked("High inconsistent with OHLC")
        if not (data.Low <= data[["Open", "Close", "High"]].min(axis=1)).all():
            return blocked("Low inconsistent with OHLC")
        window = data.tail(min_candles).reset_index(drop=True)
        if not window["timestamp"].diff().dropna().eq(pd.Timedelta(minutes=1)).all():
            return blocked("Missing candles in analysis window")
        last = window["timestamp"].iloc[-1]
        candle_end = last + pd.Timedelta(minutes=1)
        if candle_end > now:
            return blocked("In-progress or future candle")
        age = (now - candle_end).total_seconds()
        if age > max_age_seconds:
            return blocked("Stale completed candle", age)
        # Import only after validated data. No API calls, no broker interaction.
        from research.stage29_backtest import existing_strategy_on_prefix
        result = existing_strategy_on_prefix(data)
        if result not in VALID_SIGNALS:
            return blocked("Unexpected signal from strategy", age)
        return {"signal": result, "status": "VALID", "reason": "Offline research only; broker parity unverified",
                "age_seconds": age, "symbol": symbol, "timeframe": timeframe,
                "expiry_minutes": 15, "signal_time_utc": candle_end.isoformat(),
                "entry_reference_close": float(data["Close"].iloc[-1])}
    except (ValueError, TypeError, KeyError, OverflowError) as exc:
        return blocked("Invalid or unparseable data: " + type(exc).__name__)


def record_forward_snapshot(path, evaluation, *, observed_at):
    """Durable idempotent journal of observations; NEVER settle pending trades here.

    Future outcomes must be evaluated using later independent observations;
    this function deliberately does not backfill or assume execution fills.
    """
    moment = _utc(observed_at)
    if not isinstance(evaluation, dict) or evaluation.get("signal") not in VALID_SIGNALS:
        raise ValueError("Invalid evaluation")
    if evaluation.get("status") not in ("BLOCKED", "VALID"):
        raise ValueError("Invalid status")
    if evaluation["status"] != "VALID" and evaluation["signal"] != "NO TRADE":
        raise ValueError("Blocked observations cannot contain directional signals")
    item = {"observed_at_utc": moment.isoformat(), **evaluation,
            "analysis_only": True, "execution_enabled": False,
            "outcome": "NOT_EVALUATED"}
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        lines = path.read_text(encoding="utf8").splitlines()
        entries = [json.loads(s) for s in lines if s.strip()]
    else:
        entries = []
    if entries:
        previous = _utc(entries[-1]["observed_at_utc"])
        if moment < previous:
            raise ValueError("Observation chronology regression")
        if moment == previous:
            if entries[-1] == item:
                return False
            raise ValueError("Conflicting observation at existing timestamp")
    # Replace atomically instead of risking a partially written append.
    tmp = None
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf8",
                                         dir=path.parent, delete=False) as f:
            tmp = Path(f.name)
            os.fchmod(f.fileno(), 0o600)
            for entry in entries + [item]:
                f.write(json.dumps(entry, sort_keys=True) + "\\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    finally:
        if tmp is not None:
            tmp.unlink(missing_ok=True)
    return True
