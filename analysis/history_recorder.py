"""SQLite storage for research-only, deduplicated completed-candle snapshots."""
import json
import math
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

DB_PATH = Path('data/analysis_history/market_history.db')


def _number(value):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _timestamp(value):
    stamp = pd.to_datetime(value, utc=True, errors='raise')
    if pd.isna(stamp):
        raise ValueError('Missing completed candle timestamp')
    return stamp.isoformat().replace('+00:00', 'Z')


def _init(conn):
    conn.execute('''CREATE TABLE IF NOT EXISTS analysis_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        recorded_at TEXT NOT NULL,
        symbol TEXT NOT NULL,
        timeframe TEXT NOT NULL,
        market_condition TEXT NOT NULL,
        explanation TEXT NOT NULL,
        ema_9 REAL,
        ema_21 REAL,
        rsi_14 REAL,
        indicators_json TEXT NOT NULL
    )''')
    existing = {row[1] for row in conn.execute('PRAGMA table_info(analysis_history)')}
    for name in ('candle_timestamp TEXT', 'close_price REAL', 'macd REAL',
                 'macd_signal REAL', 'atr_14 REAL'):
        column = name.split()[0]
        if column not in existing:
            conn.execute(f'ALTER TABLE analysis_history ADD COLUMN {name}')
    conn.execute('''CREATE UNIQUE INDEX IF NOT EXISTS ux_history_completed_candle
        ON analysis_history(symbol, timeframe, candle_timestamp)
        WHERE candle_timestamp IS NOT NULL''')


def save_analysis(symbol: str, timeframe: str, analysis: dict,
                  assessment: dict, db_path: Path = DB_PATH) -> int:
    """Insert a snapshot once per completed candle; return existing ID on retry."""
    frame = analysis['frame']
    if not isinstance(frame, pd.DataFrame) or frame.empty or 'timestamp' not in frame:
        raise ValueError('Analysis requires a nonempty frame with candle timestamps')
    candle_timestamp = _timestamp(frame.iloc[-1]['timestamp'])
    latest = analysis['latest']
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path, timeout=15) as conn:
        _init(conn)
        cursor = conn.execute('''INSERT OR IGNORE INTO analysis_history (
            recorded_at, symbol, timeframe, market_condition, explanation,
            ema_9, ema_21, rsi_14, indicators_json, candle_timestamp,
            close_price, macd, macd_signal, atr_14
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''', (
            datetime.now(timezone.utc).isoformat(), symbol, timeframe,
            assessment['condition'], assessment['explanation'],
            _number(latest.get('EMA_9')), _number(latest.get('EMA_21')),
            _number(latest.get('RSI_14')),
            json.dumps({
                'ema_view': assessment.get('ema_view'),
                'rsi_view': assessment.get('rsi_view'),
                'macd_view': assessment.get('macd_view'),
            }), candle_timestamp, _number(latest.get('Close')),
            _number(latest.get('MACD')), _number(latest.get('MACD_Signal')),
            _number(latest.get('ATR_14')),
        ))
        if cursor.rowcount:
            return int(cursor.lastrowid)
        row = conn.execute('''SELECT id FROM analysis_history
            WHERE symbol = ? AND timeframe = ? AND candle_timestamp = ?''',
            (symbol, timeframe, candle_timestamp)).fetchone()
        if row is None:
            raise RuntimeError('Snapshot was not saved')
        return int(row[0])


def load_history(limit: int = 100, db_path: Path = DB_PATH) -> list[dict]:
    """Return recent history records, including migrated legacy records."""
    db_path = Path(db_path)
    if not db_path.exists():
        return []
    with sqlite3.connect(db_path, timeout=15) as conn:
        conn.row_factory = sqlite3.Row
        _init(conn)
        rows = conn.execute('SELECT * FROM analysis_history ORDER BY id DESC LIMIT ?',
                            (max(1, min(int(limit), 10000)),)).fetchall()
    return [dict(row) for row in rows]
