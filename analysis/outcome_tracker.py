"""Research-only 15-minute historical close-to-close observations.

Timestamps are candle OPEN timestamps; compare exact 15-minute offsets
within a continuous, validated one-minute OHLC sequence.
"""
import math
import sqlite3
from pathlib import Path

import pandas as pd

from analysis.history_recorder import DB_PATH

HORIZON = pd.Timedelta(minutes=15)


def _prepare(frame):
    required = {'timestamp', 'Open', 'High', 'Low', 'Close'}
    if not isinstance(frame, pd.DataFrame) or not required.issubset(frame.columns):
        raise ValueError('Validated OHLC DataFrame required')
    data = frame.copy()
    data['timestamp'] = pd.to_datetime(data['timestamp'], utc=True, errors='raise')
    if data['timestamp'].isna().any() or data['timestamp'].duplicated().any():
        raise ValueError('Invalid or duplicate candle timestamps')
    data = data.sort_values('timestamp').reset_index(drop=True)
    if not data.empty:
        if (data['timestamp'].dt.second != 0).any() or (data['timestamp'].dt.microsecond != 0).any():
            raise ValueError('Candle timestamps must align to minutes')
    for col in ('Open', 'High', 'Low', 'Close'):
        data[col] = pd.to_numeric(data[col], errors='raise')
        if not data[col].map(math.isfinite).all():
            raise ValueError('Non-finite OHLC')
    if (data[['Open', 'High', 'Low', 'Close']] <= 0).any().any():
        raise ValueError('OHLC prices must be positive')
    if ((data['High'] < data[['Open', 'Close', 'Low']].max(axis=1)) | (data['Low'] > data[['Open', 'Close', 'High']].min(axis=1))).any():
        raise ValueError('Invalid OHLC range')
    return data


def calculate_15m_observations(frame):
    """Return outcomes only for contiguous 16-candle windows (1min data)."""
    data = _prepare(frame)
    results = []
    for i in range(max(0, len(data) - 15)):
        window = data.iloc[i:i + 16]
        if not window['timestamp'].diff().iloc[1:].eq(pd.Timedelta(minutes=1)).all():
            continue
        start = window.iloc[0]
        end = window.iloc[-1]
        start_price, end_price = float(start['Close']), float(end['Close'])
        results.append({
            'candle_timestamp': start['timestamp'].isoformat(),
            'outcome_timestamp': end['timestamp'].isoformat(),
            'start_close': start_price,
            'end_close': end_price,
            'return_pct': (end_price / start_price - 1) * 100,
        })
    return results


def update_15m_outcomes(frame, *, symbol, timeframe, db_path=DB_PATH):
    """Update existing history rows; never create records or fetch data.

    Requires 1min candles. Existing history timestamps must match the
    canonical UTC ISO format emitted by pandas.Timestamp.isoformat().
    """
    if timeframe != '1min':
        raise ValueError('15-minute outcome tracker currently requires 1min candles')
    observations = calculate_15m_observations(frame)
    path = Path(db_path)
    if not path.exists():
        return 0
    with sqlite3.connect(path) as conn:
        cols = {row[1] for row in conn.execute('PRAGMA table_info(analysis_history)')}
        if not {'candle_timestamp', 'symbol', 'timeframe'}.issubset(cols):
            raise ValueError('Stage 7.7 history schema required')
        for name, dtype in (
            ('outcome_timestamp', 'TEXT'),
            ('outcome_close', 'REAL'),
            ('outcome_return_pct', 'REAL'),
        ):
            if name not in cols:
                conn.execute(f'ALTER TABLE analysis_history ADD COLUMN {name} {dtype}')
        changed = 0
        for item in observations:
            # Match by parsed timestamps rather than text formatting variants.
            rows = conn.execute('''SELECT id, candle_timestamp FROM analysis_history
                                   WHERE symbol=? AND timeframe=? AND candle_timestamp IS NOT NULL
                                     AND outcome_timestamp IS NULL''', (symbol, timeframe)).fetchall()
            for row_id, raw_ts in rows:
                try:
                    stored = pd.Timestamp(raw_ts)
                    if stored.tzinfo is None:
                        continue
                    matches = stored.tz_convert('UTC') == pd.Timestamp(item['candle_timestamp'])
                except (ValueError, TypeError):
                    continue
                if matches:
                    conn.execute('''UPDATE analysis_history
                        SET outcome_timestamp=?, outcome_close=?, outcome_return_pct=?
                        WHERE id=? AND outcome_timestamp IS NULL''',
                        (item['outcome_timestamp'], item['end_close'], item['return_pct'], row_id))
                    changed += 1
        return changed
