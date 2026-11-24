"""Stage 56: descriptive, leakage-aware HOLDOUT failure audit.

Offline only. Does not change signals, optimize parameters, call APIs or trade.
"""
from __future__ import annotations

import bisect
import hashlib
import json
import math
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path


def _utc(raw):
    t = raw if isinstance(raw, datetime) else datetime.fromisoformat(str(raw).replace('Z', '+00:00'))
    if t.tzinfo is None or t.utcoffset() is None:
        raise ValueError('Naive timestamp is unsafe')
    return t.astimezone(timezone.utc)


def _candle_index(frame):
    needed = {'timestamp', 'Close', 'High', 'Low'}
    if not needed.issubset(frame.columns):
        raise ValueError('Missing candle columns: ' + ','.join(sorted(needed - set(frame.columns))))
    timestamps = [_utc(t) for t in frame['timestamp']]
    if any(b <= a for a, b in zip(timestamps, timestamps[1:])):
        raise ValueError('Candles not strictly chronological')
    closes = [float(v) for v in frame['Close']]
    highs = [float(v) for v in frame['High']]
    lows = [float(v) for v in frame['Low']]
    if any(not all(math.isfinite(x) for x in (c,h,l)) or not (0 < l <= c <= h)
           for c,h,l in zip(closes, highs, lows)):
        raise ValueError('Invalid candle prices')
    return timestamps, closes, highs, lows


def _context(timestamps, closes, highs, lows, entry):
    """Only candles strictly BEFORE entry, never current/exit/future candles."""
    end = bisect.bisect_left(timestamps, entry)
    if end < 21:
        return 'insufficient_prior_history', 'insufficient_prior_history'
    prior = closes[end - 21]
    last = closes[end - 1]
    move = last - prior
    if move > 0:
        trend = 'prior20_up'
    elif move < 0:
        trend = 'prior20_down'
    else:
        trend = 'prior20_flat'
    # Descriptive fixed threshold, not learned from the holdout.
    recent_ranges = [h-l for h,l in zip(highs[end-20:end], lows[end-20:end])]
    mean_range_fraction = sum(recent_ranges) / (20 * last)
    volatility = 'prior20_range_at_least_0.01pct' if mean_range_fraction >= 0.0001 else 'prior20_range_below_0.01pct'
    return trend, volatility


def analyze_trades(trades, frame, *, min_group=10, payout=0.8):
    """Preserves historical Stage29 results; never constructs new signals."""
    if type(min_group) is not int or min_group < 2:
        raise ValueError('min_group must be at least 2')
    if not isinstance(payout, (int,float)) or not math.isfinite(payout) or not 0 < payout <= 1:
        raise ValueError('Invalid payout')
    ts, closes, highs, lows = _candle_index(frame)
    groups = defaultdict(lambda: {'wins': 0, 'losses': 0, 'pushes': 0})
    events = []
    for tr in trades:
        if tr.get('partition') != 'holdout':
            continue
        direction = str(tr.get('signal', '')).upper()
        result = str(tr.get('result', '')).upper()
        if direction not in ('UP','DOWN') or result not in ('WIN','LOSS','PUSH'):
            raise ValueError('Unexpected holdout trade signal/result')
        entry, exit_ = _utc(tr['entry_time_utc']), _utc(tr['exit_time_utc'])
        if not entry < exit_:
            raise ValueError('Invalid trade timing')
        if (exit_ - entry).total_seconds() != 15*60:
            raise ValueError('Only exact 15-minute expiry is supported')
        if not (ts[0] <= entry <= ts[-1] and ts[0] <= exit_ <= ts[-1]):
            raise ValueError('Trade timestamp is outside candle coverage')
        trend, volatility = _context(ts, closes, highs, lows, entry)
        properties = {
            'direction': direction,
            'utc_session': ('asia_00_07' if entry.hour < 8 else 'europe_08_15' if entry.hour < 16 else 'americas_16_23'),
            'prior_trend': trend,
            'prior_volatility': volatility,
            'trend_alignment': ('aligned' if (direction=='UP' and trend=='prior20_up') or (direction=='DOWN' and trend=='prior20_down') else 'opposed' if trend in ('prior20_up','prior20_down') else 'unknown'),
        }
        for dimension, category in properties.items():
            groups[(dimension, category)][{'WIN':'wins','LOSS':'losses','PUSH':'pushes'}[result]] += 1
        events.append({'entry_utc': entry.isoformat(), 'exit_utc': exit_.isoformat(), 'direction': direction, 'result': result, **properties})
    events.sort(key=lambda e: e['entry_utc'])
    # non-overlap expectation for Stage29; violation is a stop, not an adjustment
    for first, second in zip(events, events[1:]):
        if second['entry_utc'] < first['exit_utc']:
            raise ValueError('Overlapping holdout entries; independence assumption invalid')
    result_groups = {}
    for (dimension, label), counts in sorted(groups.items()):
        n = counts['wins'] + counts['losses']
        result_groups.setdefault(dimension, {})[label] = {
            **counts,
            'nonpush': n,
            'win_rate': counts['wins']/n if n else None,
            'idealized_net_units': round(counts['wins']*float(payout)-counts['losses'], 8),
            'interpretation': 'DESCRIPTIVE_ONLY' if n >= min_group else 'TOO_FEW_OBSERVATIONS',
        }
    totals = {'wins': sum(e['result']=='WIN' for e in events), 'losses':sum(e['result']=='LOSS' for e in events), 'pushes':sum(e['result']=='PUSH' for e in events)}
    return {
        'status': 'DESCRIPTIVE_ONLY' if totals['wins']+totals['losses'] >= 100 else 'INSUFFICIENT_HOLDOUT',
        'holdout': {**totals, 'nonpush': totals['wins']+totals['losses'], 'idealized_net_units': round(totals['wins']*float(payout)-totals['losses'], 8)},
        'group_minimum_nonpush': min_group,
        'break_even_win_rate': 1/(1+float(payout)),
        'groups': result_groups,
        'events': events,
        'limitations': [
            'Buckets are descriptive post-hoc subsets, not validated predictive filters.',
            '20-candle context uses strictly earlier candle timestamps; exit candles are not features.',
            'Payout and close-based settlement are idealized; broker feed parity is unverified.',
            'Correlated outcomes and strategy selection can invalidate simple significance claims.',
            'No changes to the baseline strategy; independent future tests required before tuning.',
        ],
        'live_signal': 'NO TRADE', 'execution_enabled': False, 'http_requests': 0,
    }


def build_failure_report(csv_path, *, payout=0.8, min_group=10):
    from research.stage29_backtest import load_candles, backtest
    from scripts.run_stage45_dataset_audit import parse_candles, quality
    path = Path(csv_path)
    raw = path.read_bytes()
    quality_result = quality(parse_candles(path))
    if not quality_result['continuous_one_minute_candles']:
        raise ValueError('Candle quality failed')
    frame = load_candles(path)
    baseline = backtest(frame, payout=payout)
    report = analyze_trades(baseline['trades'], frame, min_group=min_group, payout=payout)
    h = baseline['holdout']
    for k in ('wins','losses','pushes'):
        if report['holdout'][k] != h[k]:
            raise ValueError('Holdout counts do not match Stage29 baseline')
    report.update({'source': str(path), 'source_sha256': hashlib.sha256(raw).hexdigest(),
                   'candles': len(frame), 'baseline': 'existing_stage29_unmodified',
                   'quality_pass': True, 'method': baseline['method']})
    return report
