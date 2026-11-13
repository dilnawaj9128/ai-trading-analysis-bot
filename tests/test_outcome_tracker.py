from datetime import datetime, timedelta, timezone
import sqlite3

import pandas as pd
import pytest

from analysis.outcome_tracker import (
    calculate_15m_observations,
    update_15m_outcomes,
)


def candles(n=20):
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    return pd.DataFrame([
        {
            "timestamp": start + timedelta(minutes=i),
            "Open": 100 + i,
            "High": 102 + i,
            "Low": 99 + i,
            "Close": 101 + i,
        }
        for i in range(n)
    ])


def test_exact_15_minute_horizon():
    result = calculate_15m_observations(candles(16))
    assert len(result) == 1
    assert result[0]["start_close"] == 101
    assert result[0]["end_close"] == 116


def test_gap_blocks_outcome():
    frame = candles(16)
    frame.loc[8:, "timestamp"] += timedelta(minutes=1)
    assert calculate_15m_observations(frame) == []


def test_fewer_than_16_candles():
    assert calculate_15m_observations(candles(15)) == []


def test_duplicate_timestamps_rejected():
    frame = candles(16)
    frame.loc[2, "timestamp"] = frame.loc[1, "timestamp"]
    with pytest.raises(ValueError):
        calculate_15m_observations(frame)


def test_update_existing_row_idempotent(tmp_path):
    db = tmp_path / "history.db"

    with sqlite3.connect(db) as conn:
        conn.execute("""
            CREATE TABLE analysis_history (
                id INTEGER PRIMARY KEY,
                symbol TEXT,
                timeframe TEXT,
                candle_timestamp TEXT
            )
        """)
        conn.execute(
            "INSERT INTO analysis_history VALUES (1, ?, ?, ?)",
            (
                "EUR/USD",
                "1min",
                candles(16).iloc[0]["timestamp"].isoformat(),
            ),
        )

    assert update_15m_outcomes(
        candles(16),
        symbol="EUR/USD",
        timeframe="1min",
        db_path=db,
    ) == 1

    assert update_15m_outcomes(
        candles(16),
        symbol="EUR/USD",
        timeframe="1min",
        db_path=db,
    ) == 0

    with sqlite3.connect(db) as conn:
        result = conn.execute(
            "SELECT outcome_close FROM analysis_history WHERE id=1"
        ).fetchone()

    assert result[0] == 116
