from datetime import datetime, timedelta, timezone
import json

import pandas as pd
import pytest

from research.stage32_forward_safety import assess_snapshot, record_forward_snapshot


NOW = datetime(2026, 11, 19, 14, 0, tzinfo=timezone.utc)


def candles(now=NOW, n=100):
    # Last candle opens at NOW: intentionally incomplete.
    end = pd.Timestamp(now).floor("min")
    times = pd.date_range(end=end, periods=n, freq="min", tz="UTC")
    prices = [1.1 + i * 0.00001 for i in range(n)]
    return pd.DataFrame({
        "timestamp": times,
        "Open": prices,
        "High": [x + 0.0001 for x in prices],
        "Low": [x - 0.0001 for x in prices],
        "Close": prices,
    })


def test_unverified_source_blocks_even_valid_candles():
    df = candles()
    result = assess_snapshot(df, observed_at=NOW)
    assert result["signal"] == "NO TRADE"
    assert result["status"] == "BLOCKED"


def test_incomplete_candle_blocks_even_with_verified_upstream(monkeypatch):
    df = candles()
    result = assess_snapshot(df, observed_at=NOW, source_verified=True, feed_mode="live")
    assert result["status"] == "BLOCKED"
    assert "In-progress" in result["reason"]


def test_stale_data_blocks(monkeypatch):
    df = candles(now=NOW - timedelta(hours=1))
    result = assess_snapshot(df, observed_at=NOW, source_verified=True, feed_mode="live")
    assert result["status"] == "BLOCKED"
    assert "Stale" in result["reason"]


def test_gap_blocks():
    df = candles()
    df.loc[70:, "timestamp"] += pd.Timedelta(minutes=2)
    result = assess_snapshot(df, observed_at=NOW + timedelta(minutes=4),
                             source_verified=True, feed_mode="delayed")
    assert result["status"] == "BLOCKED"
    assert "Missing candles" in result["reason"]


def test_valid_completed_snapshot_calls_analysis(monkeypatch):
    df = candles()
    df["timestamp"] -= pd.Timedelta(minutes=1)
    monkeypatch.setattr("research.stage29_backtest.existing_strategy_on_prefix", lambda _: "DOWN")
    result = assess_snapshot(df, observed_at=NOW, source_verified=True, feed_mode="live")
    assert result["status"] == "VALID"
    assert result["signal"] == "DOWN"


def test_duplicate_timestamp_is_blocked():
    df = candles()
    df.loc[10, "timestamp"] = df.loc[9, "timestamp"]
    assert assess_snapshot(df, observed_at=NOW)["signal"] == "NO TRADE"
    result = assess_snapshot(df, observed_at=NOW, source_verified=True, feed_mode="live")
    assert result["status"] == "BLOCKED"


def test_journal_idempotency_and_chronology(tmp_path):
    file = tmp_path / "forward.jsonl"
    evaluation = {"signal": "NO TRADE", "status": "BLOCKED", "reason": "Unverified"}
    assert record_forward_snapshot(file, evaluation, observed_at=NOW)
    assert record_forward_snapshot(file, evaluation, observed_at=NOW) is False
    assert len(file.read_text().splitlines()) == 1
    assert json.loads(file.read_text().splitlines()[0])["outcome"] == "NOT_EVALUATED"
    with pytest.raises(ValueError, match="chronology"):
        record_forward_snapshot(file, evaluation, observed_at=NOW - timedelta(minutes=1))


def test_journal_rejects_blocked_directional_signal(tmp_path):
    with pytest.raises(ValueError, match="Blocked"):
        record_forward_snapshot(
            tmp_path / "record.jsonl",
            {"status": "BLOCKED", "signal": "UP"},
            observed_at=NOW,
        )
