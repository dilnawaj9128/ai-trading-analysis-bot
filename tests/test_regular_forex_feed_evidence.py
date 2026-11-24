"""Offline checks for regular Forex feed-class evidence boundaries."""
from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest

from market_data.regular_forex_feed_evidence import (
    FeedEvidenceError, classify_authorized_fetch, classify_saved_csv,
)

BASE = datetime(2026, 11, 24, 12, 0, tzinfo=timezone.utc)

def sample():
    times = [BASE + timedelta(minutes=i) for i in range(120)]
    frame = pd.DataFrame({
        "timestamp": times, "Open": [1.1] * 120,
        "High": [1.1002] * 120, "Low": [1.0998] * 120,
        "Close": [1.1001] * 120,
    })
    return {
        "frame": frame, "symbol": "EUR/USD", "interval": "1min",
        "analysis_only": True, "execution_enabled": False,
        "candles": 120, "stale": False, "gaps": 0,
        "age_seconds": 133.6,
        "latest_utc": times[-1].isoformat(),
    }

def test_valid_fetch_classifies_catalog_but_not_account_or_broker():
    report = classify_authorized_fetch(sample())
    assert report["status"].startswith("PROVIDER_DOCUMENTED_REALTIME")
    assert report["observed_delay_after_close_seconds"] == pytest.approx(73.6)
    assert report["provider_classification_verified_from_official_docs"] is True
    assert report["account_specific_live_mode_verified"] is False
    assert report["directional_signal_authorized"] is False
    assert report["live_signal"] == "NO TRADE"

def test_non_forex_or_execution_enabled_fails():
    s = sample()
    s["symbol"] = "EUR/USD OTC"
    with pytest.raises(FeedEvidenceError):
        classify_authorized_fetch(s)
    s = sample()
    s["execution_enabled"] = True
    with pytest.raises(FeedEvidenceError):
        classify_authorized_fetch(s)

def test_incomplete_age_or_gap_fails():
    s = sample()
    s["age_seconds"] = 30
    with pytest.raises(FeedEvidenceError):
        classify_authorized_fetch(s)
    s = sample()
    s["gaps"] = 1
    with pytest.raises(FeedEvidenceError):
        classify_authorized_fetch(s)

def test_saved_csv_audit_with_hash(tmp_path):
    from hashlib import sha256
    f = tmp_path / "snapshot.csv"
    s = sample()
    s["frame"].to_csv(f, index=False)
    digest = sha256(f.read_bytes()).hexdigest()
    report = classify_saved_csv(
        f, expected_sha256=digest,
        now=BASE + timedelta(minutes=125)
    )
    assert report["saved_csv_matches_pinned_sha256"] is True
    assert report["candles"] == 120
    assert report["account_specific_live_mode_verified"] is False
    assert report["actual_post_close_latency_from_csv"] is None

def test_saved_csv_tamper_detected(tmp_path):
    f = tmp_path / "snapshot.csv"
    sample()["frame"].to_csv(f, index=False)
    with pytest.raises(FeedEvidenceError):
        classify_saved_csv(f, expected_sha256="0" * 64)
