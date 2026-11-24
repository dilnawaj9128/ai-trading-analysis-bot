"""Offline Stage 59 feed comparison regression tests."""
import csv
from datetime import datetime, timedelta, timezone

import pytest

from scripts.run_stage59_feed_audit import (
    FeedComparisonError, compare, load_candles,
)


NOW = datetime(2026, 11, 24, 15, 0, tzinfo=timezone.utc)


def candles(path, *, shift=0, count=60, offset_pips=0, naive=False):
    with path.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["timestamp", "Open", "High", "Low", "Close"])
        for i in range(count):
            ts = NOW - timedelta(minutes=count + 2 - i)
            stamp = ts.strftime("%Y-%m-%dT%H:%M:%SZ")
            if naive:
                stamp = stamp.removesuffix("Z")
            price = 1.1000 + i * 0.00001 + offset_pips * 0.0001
            writer.writerow([
                stamp, f"{price:.6f}", f"{price + 0.0002:.6f}",
                f"{price - 0.0002:.6f}", f"{price + 0.00005:.6f}",
            ])


def test_missing_broker_is_unverified(tmp_path):
    provider = tmp_path / "provider.csv"
    candles(provider)
    report = compare(provider, tmp_path / "broker.csv", now=NOW, provider_attested=True)
    assert report["status"] == "UNVERIFIED"
    assert report["live_signal"] == "NO TRADE"
    assert report["no_http_requests"] is True


def test_identical_csv_is_descriptive_only(tmp_path):
    provider, broker = tmp_path / "provider.csv", tmp_path / "broker.csv"
    candles(provider)
    candles(broker)
    report = compare(
        provider, broker, broker_market="regular", now=NOW,
        provider_attested=True,
    )
    assert report["status"] == "DESCRIPTIVE_MATCH_ONLY"
    assert report["matched_candles"] == 60
    assert report["max_close_difference_pips"] == 0
    assert report["broker_parity_verified"] is False
    assert report["live_signal"] == "NO TRADE"


def test_diverging_prices_rejected(tmp_path):
    provider, broker = tmp_path / "provider.csv", tmp_path / "broker.csv"
    candles(provider)
    candles(broker, offset_pips=4)
    report = compare(
        provider, broker, broker_market="regular", now=NOW,
        provider_attested=True,
    )
    assert report["status"] == "UNVERIFIED"
    assert report["reason"] == "OBSERVED_CLOSE_PRICES_DIVERGE"


def test_otc_not_regular_forex_parity(tmp_path):
    provider, broker = tmp_path / "provider.csv", tmp_path / "broker.csv"
    candles(provider)
    candles(broker)
    report = compare(
        provider, broker, broker_market="otc", now=NOW,
        provider_attested=True,
    )
    assert report["status"] == "UNVERIFIED"
    assert report["reason"].startswith("OTC_MARKET")


def test_naive_timezone_rejected(tmp_path):
    path = tmp_path / "broker.csv"
    candles(path, naive=True)
    with pytest.raises(FeedComparisonError, match="UTC offset"):
        load_candles(path, now=NOW)


def test_candles_not_yet_complete_rejected(tmp_path):
    path = tmp_path / "broker.csv"
    candles(path, count=60)
    with pytest.raises(FeedComparisonError, match="Future or incomplete"):
        load_candles(path, now=NOW - timedelta(minutes=5))
