"""Persistent, idempotent 1-min research candle storage; zero HTTP/orders."""
from __future__ import annotations
import sqlite3
from pathlib import Path
import pandas as pd
from dashboard.real_data_mode import validate_ohlc

DEFAULT_DB = Path('data/real_market/eurusd_candles.sqlite3')


def save_capture(frame, db_path=DEFAULT_DB, *, now=None):
    clean, quality = validate_ohlc(frame, now=now)
    if quality['quality'] != 'PASS' or quality['stale']:
        raise ValueError('Rejecting gapped or stale capture; existing history remains unchanged')
    db = Path(db_path)
    db.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db, timeout=15) as con:
        con.execute('PRAGMA busy_timeout=15000')
        con.execute('''CREATE TABLE IF NOT EXISTS candles (
            utc_open TEXT PRIMARY KEY, open REAL NOT NULL, high REAL NOT NULL,
            low REAL NOT NULL, close REAL NOT NULL)''')
        con.execute('''CREATE TABLE IF NOT EXISTS capture_audit (
            id INTEGER PRIMARY KEY AUTOINCREMENT, recorded_utc TEXT NOT NULL,
            newest_open_utc TEXT NOT NULL, rows INTEGER NOT NULL, inserted INTEGER NOT NULL,
            source TEXT NOT NULL)''')
        before = con.total_changes
        for rec in clean.itertuples(index=False):
            con.execute('''INSERT OR IGNORE INTO candles
                (utc_open,open,high,low,close) VALUES (?,?,?,?,?)''',
                (rec.timestamp.isoformat(), float(rec.Open), float(rec.High),
                 float(rec.Low), float(rec.Close)))
        inserted = con.total_changes - before
        # Never silently revise a previously stored candle: spot conflicting prices.
        for rec in clean.itertuples(index=False):
            existing = con.execute('SELECT open,high,low,close FROM candles WHERE utc_open=?',
                                   (rec.timestamp.isoformat(),)).fetchone()
            incoming = (float(rec.Open),float(rec.High),float(rec.Low),float(rec.Close))
            if any(abs(x-y) > 0.00000001 for x,y in zip(existing,incoming)):
                raise ValueError('Conflicting historical provider candle; rolled back')
        from datetime import datetime, timezone
        con.execute('''INSERT INTO capture_audit
            (recorded_utc,newest_open_utc,rows,inserted,source) VALUES (?,?,?,?,?)''',
            (datetime.now(timezone.utc).isoformat(), clean['timestamp'].iloc[-1].isoformat(),
             len(clean), inserted, 'TWELVE_DATA_UNVERIFIED_FEED_MODE'))
    return {'inserted': inserted, 'received':len(clean), 'latest_open_utc':quality['latest_completed_open_utc']}


def load_history(db_path=DEFAULT_DB, *, limit=2000):
    db = Path(db_path)
    if not db.exists():
        return pd.DataFrame(columns=['timestamp','Open','High','Low','Close'])
    with sqlite3.connect(db) as con:
        rows = con.execute('''SELECT utc_open,open,high,low,close FROM
            (SELECT * FROM candles ORDER BY utc_open DESC LIMIT ?)
            ORDER BY utc_open ASC''', (int(limit),)).fetchall()
    result = pd.DataFrame(rows, columns=['timestamp','Open','High','Low','Close'])
    if not result.empty:
        result['timestamp'] = pd.to_datetime(result['timestamp'], utc=True)
    return result


def resample_history(frame, minutes=1):
    if minutes not in (1,3,5):
        raise ValueError('Only 1, 3 and 5-minute views supported')
    if frame.empty or minutes == 1:
        return frame.copy()
    d=frame.set_index('timestamp').sort_index()
    # Never fabricate full candles from incomplete buckets or through a gap.
    rule=f'{minutes}min'
    grouped=d.resample(rule, label='left',closed='left')
    result=grouped.agg({'Open':'first','High':'max','Low':'min','Close':'last'})
    counts=grouped['Close'].count()
    result=result[counts==minutes].dropna().reset_index()
    return result


def history_health(frame):
    if frame.empty:
        return {'rows':0,'missing_minutes':0,'last_open_utc':None}
    delta=frame['timestamp'].diff().dropna().dt.total_seconds().div(60)
    gaps=int((delta-1).clip(lower=0).sum())
    return {'rows':len(frame),'missing_minutes':gaps,
            'last_open_utc':frame['timestamp'].iloc[-1].isoformat()}
