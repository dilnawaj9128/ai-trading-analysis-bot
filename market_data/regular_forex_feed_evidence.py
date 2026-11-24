"""Evidence-based classification for Twelve Data REGULAR EUR/USD research.

The provider publishes that its Forex catalog is a real-time composite feed,
while REST 1-minute *completed candles* typically require 18-120 seconds of
post-close processing. This does NOT attest the mode of an individual account,
authorize a trading signal, or certify any broker's prices.

Official source documents:
https://twelvedata.com/exchanges/physical_currency?group=core
https://support.twelvedata.com/en/articles/12520817-forex-api-v2
https://support.twelvedata.com/en/articles/5203307-data-delays
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

DOCUMENTATION = {
    "forex_catalog": "https://twelvedata.com/exchanges/physical_currency?group=core",
    "forex_v2": "https://support.twelvedata.com/en/articles/12520817-forex-api-v2",
    "rest_candle_latency": "https://support.twelvedata.com/en/articles/5203307-data-delays",
}
TYPICAL_MIN_SECONDS = 18
TYPICAL_MAX_SECONDS = 120


class FeedEvidenceError(ValueError):
    pass


def _catalog_report():
    return {
        "provider": "Twelve Data",
        "instrument": "EUR/USD",
        "instrument_type": "REGULAR_FOREX_COMPOSITE",
        "official_catalog_feed_class": "REAL_TIME",
        "delivery": "REST_COMPLETED_1MIN_CANDLES",
        "published_typical_rest_delay_after_close_seconds": [18, 120],
        "provider_classification_verified_from_official_docs": True,
        "subscription_specific_delivery_attested": False,
        "account_specific_live_mode_verified": False,
        "broker_feed_parity_verified": False,
        "directional_signal_authorized": False,
        "live_signal": "NO TRADE",
        "no_extra_http_requests": True,
        "broker_orders": 0,
        "source_urls": DOCUMENTATION,
    }


def _validate_identity(result):
    if type(result) is not dict:
        raise FeedEvidenceError("Expected validated fetch dict")
    if (result.get("symbol") != "EUR/USD"
            or result.get("interval") != "1min"
            or result.get("analysis_only") is not True
            or result.get("execution_enabled") is not False):
        raise FeedEvidenceError("Unexpected source, instrument, or execution mode")

    frame = result.get("frame")
    if (not isinstance(frame, pd.DataFrame)
            or len(frame) < 60
            or not {"timestamp", "Open", "High", "Low", "Close"}.issubset(frame.columns)
            or result.get("candles") != len(frame)):
        raise FeedEvidenceError("Invalid candle frame or count")
    stamps = pd.to_datetime(frame["timestamp"], utc=True, errors="raise")
    if (stamps.isna().any() or stamps.duplicated().any()
            or not stamps.is_monotonic_increasing
            or (stamps.diff().dropna() != pd.Timedelta(minutes=1)).any()
            or (stamps.dt.second != 0).any()
            or (stamps.dt.microsecond != 0).any()):
        raise FeedEvidenceError("Invalid timestamp chronology")

    try:
        published_latest = pd.Timestamp(result["latest_utc"])
    except (KeyError, TypeError, ValueError) as exc:
        raise FeedEvidenceError("Missing latest UTC timestamp") from exc
    if published_latest.tzinfo is None or published_latest.utcoffset() is None:
        raise FeedEvidenceError("Latest candle missing UTC timezone")
    if stamps.iloc[-1] != published_latest.tz_convert("UTC"):
        raise FeedEvidenceError("Latest candle metadata mismatch")

    if result.get("gaps") != 0 or result.get("stale") is not False:
        raise FeedEvidenceError("Gapped or stale candle snapshot")
    try:
        open_age = float(result["age_seconds"])
    except (KeyError, TypeError, ValueError) as exc:
        raise FeedEvidenceError("Missing fetch-age evidence") from exc
    if not (60 <= open_age <= 180):
        raise FeedEvidenceError("Candle must be completed and fresh")
    return open_age - 60, len(frame), stamps.iloc[-1].isoformat()


def classify_authorized_fetch(result):
    """Classify already-fetched data in memory; never send an HTTP request."""
    lag, count, latest = _validate_identity(result)
    report = _catalog_report()
    report.update({
        "status": "PROVIDER_DOCUMENTED_REALTIME_CLASS_AND_FRESH_REST_SNAPSHOT",
        "source_evidence": "VALIDATED_AUTHORIZED_FETCH_RESULT",
        "source_attestation_scope": "symbol, interval, completed-candle freshness only",
        "candles": count,
        "latest_candle_open_utc": latest,
        "observed_delay_after_close_seconds": round(lag, 2),
        "observed_within_typical_rest_delay": TYPICAL_MIN_SECONDS <= lag <= TYPICAL_MAX_SECONDS,
        "delivery_quality_verified_at_fetch": True,
        "provider_response_explicit_mode_attested": False,
    })
    # Deliberately leave the existing strategy's data_mode=unknown unchanged.
    return report


def classify_saved_csv(path, *, expected_sha256=None, now=None):
    """Offline catalog classification + integrity/quality audit of saved CSV.

    The CSV lacks original HTTP receipt/metadata and fetch wallclock. Do not
    infer what the account was entitled to or how late it arrived.
    """
    from scripts.run_stage59_feed_audit import load_candles
    path = Path(path)
    raw = path.read_bytes()
    sha = hashlib.sha256(raw).hexdigest()
    if expected_sha256 is not None:
        if (type(expected_sha256) is not str or len(expected_sha256) != 64
                or any(c not in "0123456789abcdef" for c in expected_sha256)):
            raise FeedEvidenceError("Invalid SHA256 pin")
        if sha != expected_sha256:
            raise FeedEvidenceError("Saved capture differs from the supplied SHA256")
    capture = load_candles(path, now=now)
    if capture["gaps"]:
        raise FeedEvidenceError("Saved capture contains missing candle intervals")
    if len(capture["rows"]) < 60:
        raise FeedEvidenceError("At least 60 candles required")
    report = _catalog_report()
    report.update({
        "status": "PROVIDER_CATALOG_CLASS_VERIFIED_SAVED_CAPTURE_QUALITY_PASSED",
        "source_evidence": "LOCAL_CSV_ONLY_NOT_INDEPENDENTLY_ATTESTED",
        "saved_csv_path": str(path),
        "saved_csv_sha256": sha,
        "saved_csv_matches_pinned_sha256": expected_sha256 is not None,
        "candles": len(capture["rows"]),
        "latest_candle_open_utc": capture["latest_utc"],
        "saved_candle_gaps": capture["gaps"],
        "saved_capture_quality_verified": True,
        "actual_post_close_latency_from_csv": None,
        "delivery_quality_verified_at_fetch": False,
        "provider_response_explicit_mode_attested": False,
    })
    return report
