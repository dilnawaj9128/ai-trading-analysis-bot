"""Persist the already-authorized EUR/USD 1m research frame with zero extra HTTP.

Call only after fetch_authorized_live_candles returns a validated result.
A local CSV proves neither broker parity nor any directional accuracy.
"""
from __future__ import annotations

import hashlib
import math
import os
import tempfile
from pathlib import Path

import pandas as pd


class ResearchCaptureError(ValueError):
    pass


def save_verified_research_frame(result, *, directory=Path("data/research/provider_captures")):
    """Write-once saved research CSV. Does not call a provider or settle credits."""
    if (type(result) is not dict
            or result.get("analysis_only") is not True
            or result.get("execution_enabled") is not False
            or result.get("symbol") != "EUR/USD"
            or result.get("interval") != "1min"
            or result.get("stale") is not False
            or result.get("gaps") != 0):
        raise ResearchCaptureError("Unverified/stale research fetch result")

    frame = result.get("frame")
    cols = ["timestamp", "Open", "High", "Low", "Close"]
    if not isinstance(frame, pd.DataFrame) or not set(cols).issubset(frame.columns):
        raise ResearchCaptureError("Completed candle frame missing")
    if type(result.get("candles")) is not int or len(frame) != result["candles"] or len(frame) < 60:
        raise ResearchCaptureError("Insufficient or mismatched candle count")

    clean = frame[cols].copy(deep=True)
    stamps = pd.to_datetime(clean["timestamp"], utc=True, errors="raise")
    if (stamps.isna().any() or stamps.duplicated().any()
            or not stamps.is_monotonic_increasing
            or (stamps.diff().dropna() != pd.Timedelta(minutes=1)).any()
            or (stamps.dt.second != 0).any()
            or (stamps.dt.microsecond != 0).any()):
        raise ResearchCaptureError("Invalid or noncontiguous candle timestamps")

    for key in cols[1:]:
        clean[key] = pd.to_numeric(clean[key], errors="raise")
        if not clean[key].map(math.isfinite).all() or (clean[key] <= 0).any():
            raise ResearchCaptureError("Invalid OHLC price")

    if (not (clean["High"] >= clean[["Open", "Low", "Close"]].max(axis=1)).all()
            or not (clean["Low"] <= clean[["Open", "High", "Close"]].min(axis=1)).all()):
        raise ResearchCaptureError("Invalid OHLC relationship")

    if stamps.iloc[-1].isoformat() != pd.Timestamp(result.get("latest_utc")).isoformat():
        raise ResearchCaptureError("Latest candle timestamp mismatch")

    clean["timestamp"] = stamps.dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    csv_bytes = clean.to_csv(index=False, float_format="%.8f", lineterminator="\n").encode("utf-8")
    sha = hashlib.sha256(csv_bytes).hexdigest()
    latest = stamps.iloc[-1].strftime("%Y%m%dT%H%M%SZ")
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    if directory.is_symlink():
        raise ResearchCaptureError("Capture directory cannot be a symlink")

    filename = "twelve_data_eurusd_1min_" + latest + "_" + sha[:12] + ".csv"
    target = directory / filename
    if target.is_symlink():
        raise ResearchCaptureError("Capture path redirected")
    if target.exists():
        if hashlib.sha256(target.read_bytes()).hexdigest() != sha:
            raise ResearchCaptureError("Capture filename collision with differing data")
        return {"csv_path": str(target), "csv_sha256": sha, "csv_saved": "ALREADY_EXISTS",
                "extra_http_requests": 0, "broker_parity_verified": False}

    temp = None
    try:
        with tempfile.NamedTemporaryFile(mode="wb", dir=directory, prefix=".capture_",
                                         suffix=".tmp", delete=False) as h:
            temp = Path(h.name)
            os.fchmod(h.fileno(), 0o600)
            h.write(csv_bytes)
            h.flush()
            os.fsync(h.fileno())
        try:
            os.link(temp, target)
        except FileExistsError:
            if hashlib.sha256(target.read_bytes()).hexdigest() != sha:
                raise ResearchCaptureError("Conflicting existing capture")
        directory_fd = os.open(directory, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        if temp is not None:
            temp.unlink(missing_ok=True)

    return {"csv_path": str(target), "csv_sha256": sha, "csv_saved": "SAVED",
            "extra_http_requests": 0, "broker_parity_verified": False}
