"""One-shot, consent-bound REAL EUR/USD data visualization. No signal engine.

Existing provider guards are authoritative; no requests on import/preview,
no retries, no broker access, no modification of credit journals.
"""
from __future__ import annotations

from datetime import datetime, timezone, timedelta
from pathlib import Path
import math
import pandas as pd

COLUMNS = ('timestamp','Open','High','Low','Close')


def validate_ohlc(frame: pd.DataFrame, *, now=None, min_rows=60):
    if not isinstance(frame, pd.DataFrame) or not set(COLUMNS).issubset(frame.columns):
        raise ValueError('Validated OHLC DataFrame required')
    if len(frame) < min_rows:
        raise ValueError('Insufficient candles')
    now = now or datetime.now(timezone.utc)
    if not isinstance(now, datetime) or now.tzinfo is None or now.utcoffset() is None:
        raise ValueError('UTC-aware clock required')
    now = now.astimezone(timezone.utc)
    clean = frame.loc[:, COLUMNS].copy(deep=True)
    raw_stamps = clean['timestamp']
    if not isinstance(raw_stamps.dtype, pd.DatetimeTZDtype):
        if not raw_stamps.astype(str).str.contains(r'(?:Z|[+-]\d\d:\d\d)$', regex=True).all():
            raise ValueError('Candle timestamps must include UTC offsets')
    clean['timestamp'] = pd.to_datetime(raw_stamps, utc=True, errors='raise')
    stamp = clean['timestamp']
    if stamp.isna().any() or stamp.duplicated().any() or not stamp.is_monotonic_increasing:
        raise ValueError('Invalid chronological candles')
    if (stamp.dt.second != 0).any() or (stamp.dt.microsecond != 0).any():
        raise ValueError('Expected one-minute UTC candle boundaries')
    for name in COLUMNS[1:]:
        clean[name] = pd.to_numeric(clean[name], errors='raise')
        if not clean[name].map(lambda x: math.isfinite(float(x)) and float(x) > 0).all():
            raise ValueError('Invalid OHLC prices')
    if not (clean['High'] >= clean[['Open','Low','Close']].max(axis=1)).all():
        raise ValueError('Invalid OHLC high')
    if not (clean['Low'] <= clean[['Open','High','Close']].min(axis=1)).all():
        raise ValueError('Invalid OHLC low')
    delta = stamp.diff().dropna()
    gaps = int((delta != pd.Timedelta(minutes=1)).sum())
    age_seconds = (pd.Timestamp(now) - (stamp.iloc[-1] + pd.Timedelta(minutes=1))).total_seconds()
    if age_seconds < 0:
        raise ValueError('Last candle is not completed')
    return clean, {'quality': 'PASS' if gaps == 0 else 'GAPS_DETECTED',
                   'gaps': gaps, 'age_seconds': round(float(age_seconds), 1),
                   'stale': age_seconds > 180,
                   'latest_completed_open_utc': stamp.iloc[-1].isoformat(),
                   'latest_completed_close_utc': (stamp.iloc[-1]+pd.Timedelta(minutes=1)).isoformat(),
                   'rows': len(clean)}


def analyze_frame(frame: pd.DataFrame, *, now=None, indicator_fn=None):
    clean, quality = validate_ohlc(frame, now=now)
    if indicator_fn is None:
        from indicators import calculate_indicators
        indicator_fn = calculate_indicators
    enriched = indicator_fn(clean.copy(deep=True))
    if not isinstance(enriched, pd.DataFrame) or len(enriched) != len(clean):
        raise ValueError('Indicator engine returned unexpected candle count')
    last = enriched.iloc[-1]
    keys = ('Close', 'EMA_9','EMA_20','EMA_21','EMA_50','RSI_14','MACD','MACD_signal','ATR_14')
    values = {}
    for key in keys:
        if key in last:
            try:
                val = float(last[key])
                if math.isfinite(val):
                    values[key] = val
            except (ValueError,TypeError):
                pass
    return {'frame': clean, 'enriched': enriched, 'quality': quality,
            'indicators': values, 'signal_generation': False,
            'broker_orders': 0, 'source': 'TWELVE_DATA_GUARDED_FETCH'}


def fetch_real_data_once(*, approved=False, api_key=None, credit_loader=None,
                         renewal=None, fetcher=None, now=None, indicator_fn=None):
    """At most 2 accounted provider requests (optional renewal + OHLC fetch)."""
    if approved is not True or not api_key or not str(api_key).strip():
        raise ValueError('Explicit approved API access and local key required')
    if credit_loader is None:
        from market_data.provider_credit_state import load_credit_state
        credit_loader = load_credit_state
    if fetcher is None:
        from market_data.authorized_live_fetch import fetch_authorized_live_candles
        fetcher = fetch_authorized_live_candles
    from config.market_config import create_research_config
    renewed = False
    if credit_loader() is None:
        if renewal is None:
            from market_data.verified_credit_renewal import renew_verified_credits_once
            renewal = renew_verified_credits_once
        renewal(approved=True, api_key=api_key)
        renewed = True
    config = create_research_config('quotex', 'forex', 'EUR/USD', '1min', 15)
    response = fetcher(config, api_key=api_key)
    if not isinstance(response, dict) or response.get('analysis_only') is not True or response.get('execution_enabled') is not False:
        raise ValueError('Unsafe or invalid provider response')
    if response.get('symbol') != 'EUR/USD' or response.get('interval') != '1min':
        raise ValueError('Unexpected market feed')
    if not isinstance(response.get('candles'), int) or response.get('candles') != len(response.get('frame', [])):
        raise ValueError('Candle count mismatch')
    result = analyze_frame(response['frame'], now=now, indicator_fn=indicator_fn)
    result['renewal_used'] = renewed
    result['max_http_requests'] = 2
    return result
