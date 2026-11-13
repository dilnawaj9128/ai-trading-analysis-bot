"""Tests for Stage 7.7 snapshot migration and deduplication."""
import sqlite3
import pandas as pd
from analysis.history_recorder import load_history, save_analysis


def sample(timestamp='2026-11-13T02:10:00Z'):
    return ({'frame': pd.DataFrame({'timestamp': [timestamp]}),
             'latest': {'Close': 1.1, 'EMA_9': 1.2, 'EMA_21': 1.1,
                        'RSI_14': 55, 'MACD': 0.01, 'ATR_14': 0.03}},
            {'condition': 'MIXED / INCONCLUSIVE', 'explanation': 'Research only.'})


def test_duplicate_candle_returns_existing_id(tmp_path):
    db = tmp_path / 'history.db'
    analysis, assessment = sample()
    first = save_analysis('EUR/USD', '1min', analysis, assessment, db)
    second = save_analysis('EUR/USD', '1min', analysis, assessment, db)
    assert first == second
    assert len(load_history(db_path=db)) == 1


def test_distinct_candle_saved(tmp_path):
    db = tmp_path / 'history.db'
    a, b = sample()
    save_analysis('EUR/USD', '1min', a, b, db)
    a, b = sample('2026-11-13T02:11:00Z')
    save_analysis('EUR/USD', '1min', a, b, db)
    assert len(load_history(db_path=db)) == 2


def test_legacy_schema_preserved(tmp_path):
    db = tmp_path / 'history.db'
    with sqlite3.connect(db) as conn:
        conn.execute('''CREATE TABLE analysis_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT, recorded_at TEXT NOT NULL,
            symbol TEXT NOT NULL, timeframe TEXT NOT NULL,
            market_condition TEXT NOT NULL, explanation TEXT NOT NULL,
            ema_9 REAL, ema_21 REAL, rsi_14 REAL, indicators_json TEXT NOT NULL)''')
        conn.execute('''INSERT INTO analysis_history
            (recorded_at, symbol, timeframe, market_condition, explanation, indicators_json)
            VALUES ('old', 'EUR/USD', '1min', 'MIXED', 'old record', '{}')''')
    a, b = sample()
    save_analysis('EUR/USD', '1min', a, b, db)
    records = load_history(db_path=db)
    assert len(records) == 2
    assert records[-1]['candle_timestamp'] is None


def test_missing_timestamp_rejected(tmp_path):
    a, b = sample()
    a['frame'] = pd.DataFrame({'Close': [1.1]})
    try:
        save_analysis('EUR/USD', '1min', a, b, tmp_path / 'db.sqlite')
    except ValueError:
        pass
    else:
        raise AssertionError('Missing timestamp must be rejected')
