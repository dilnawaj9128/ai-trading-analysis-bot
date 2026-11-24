"""Offline prospective A/B: existing ATR 0.25 vs conservative ATR 0.50.

Never imports API/broker clients, fetches data, changes production filters,
or retrospectively manufactures an observation on old candles.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import math
from datetime import datetime, timedelta, timezone
from pathlib import Path

from research.real_prediction_campaign import (
    _candles, _envelope, _load_envelope, _new_file, utc, digest,
)

JOURNAL = Path('data/research/atr_forward_comparison')
CAPTURES = Path('data/research/prospective_accuracy/captures')
FIFTEEN = timedelta(minutes=15)
MINUTE = timedelta(minutes=1)


def signals(frame):
    """Threshold 0.50 via exact distance rescaling, production engine unchanged.

    Under the existing engine, abs(level-close) <= 0.25*ATR.  Scaling
    the *distance* by 0.5 yields precisely abs(level-close) <= 0.50*ATR.
    Only last row is used by the existing engine.
    """
    from indicators import calculate_indicators
    from patterns.candlestick import detect_candlestick_patterns
    from strategy.signal_engine import generate_signal
    enriched = calculate_indicators(frame.copy())
    patterns = detect_candlestick_patterns(frame.copy())
    if 'Pattern_Direction' in patterns:
        enriched['Pattern_Direction'] = patterns['Pattern_Direction'].to_numpy()
    base = generate_signal(enriched, expiry_minutes=15, data_mode='live', data_quality_status='VALID')
    test = enriched.copy()
    row = test.iloc[-1]
    close = float(row['Close'])
    for col in ('Support', 'Resistance'):
        if col in test:
            try:
                level = float(row[col])
            except (TypeError, ValueError):
                continue
            if math.isfinite(level):
                test.at[test.index[-1], col] = close + 0.5 * (level - close)
    challenger = generate_signal(test, expiry_minutes=15, data_mode='live', data_quality_status='VALID')
    for result in (base, challenger):
        if result['signal'] not in ('UP', 'DOWN', 'NO TRADE'):
            raise ValueError('Unknown strategy output')
    return {'control_025': base['signal'], 'challenger_050': challenger['signal']}


def record(capture, *, journal=JOURNAL, now=None, max_age=180):
    """Record BEFORE future expiry; never retroactively label an old capture."""
    from research.real_prediction_campaign import _candles
    now = utc(now or datetime.now(timezone.utc))
    source, df, _ = _candles(capture)
    latest_open = utc(df.timestamp.iloc[-1])
    decision = latest_open + MINUTE
    age = (now - decision).total_seconds()
    if not 0 <= age <= max_age:
        raise ValueError('Capture is not a freshly completed candle; no retrospective recording')
    expiry = decision + FIFTEEN
    if now >= expiry:
        raise ValueError('Observation would be created after expiry')
    base = Path(journal)
    obs_dir = base / 'observations'
    obs_dir.mkdir(parents=True, exist_ok=True)
    # Same immutable candle for both arms. Fail closed if any ambiguous prior record.
    import fcntl
    with (base / '.paired_observe.lock').open('a+b') as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        for existing in obs_dir.glob('*.json'):
            prior = _load_envelope(existing, 'ATR_PAIR')
            if abs((decision - utc(prior['decision_utc'])).total_seconds()) < FIFTEEN.total_seconds():
                raise ValueError('15-minute A/B non-overlap window')
        choices = signals(df)
        payload = {
            'symbol': 'EUR/USD', 'timeframe': '1min',
            'decision_utc': decision.isoformat(), 'recorded_utc': now.isoformat(),
            'expiry_utc': expiry.isoformat(), 'entry_close': float(df.Close.iloc[-1]),
            'last_open_utc': latest_open.isoformat(),
            'source_file': str(source), 'source_sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
            'models': choices, 'live_signal': 'NO TRADE',
            'price_feed_attested': False, 'quotex_parity': False, 'broker_orders': 0,
            'research_only': True, 'max_age_at_record_sec': age,
        }
        target = obs_dir / (hashlib.sha256(decision.isoformat().encode()).hexdigest()[:24] + '.json')
        _new_file(target, _envelope('ATR_PAIR', payload))
    return target, payload


def settle(capture, *, journal=JOURNAL, now=None):
    """Exact +15m candle close, entry match and immutable paired predictions."""
    now = utc(now or datetime.now(timezone.utc))
    source, df, _ = _candles(capture)
    if utc(df.timestamp.iloc[-1]) + MINUTE > now:
        raise ValueError('Incomplete future candle')
    made = []
    base = Path(journal)
    for obsfile in sorted((base / 'observations').glob('*.json')):
        dest = base / 'settlements' / obsfile.name
        if dest.exists():
            _load_envelope(dest, 'ATR_SETTLEMENT')
            continue
        obs = _load_envelope(obsfile, 'ATR_PAIR')
        expiry = utc(obs['expiry_utc'])
        if not utc(obs['recorded_utc']) < expiry <= now:
            continue
        if expiry != utc(obs['decision_utc']) + FIFTEEN:
            raise ValueError('Bad expiry')
        ent = df[df.timestamp == utc(obs['last_open_utc'])]
        row = df[df.timestamp == expiry - MINUTE]
        if len(ent) != 1 or len(row) != 1:
            continue
        entry = float(obs['entry_close'])
        if not math.isclose(float(ent.Close.iloc[0]), entry, abs_tol=1e-10, rel_tol=0):
            raise ValueError('Entry mismatch: cannot settle')
        exit_price = float(row.Close.iloc[0])
        def score(direction):
            if direction == 'NO TRADE': return 'ABSTAINED'
            if exit_price == entry: return 'PUSH'
            return 'WIN' if ((exit_price > entry) == (direction == 'UP')) else 'LOSS'
        results = {name: score(direction) for name, direction in obs['models'].items()}
        payload = {'observation_sha256': digest(obs), 'observed_utc': now.isoformat(),
                   'expiry_utc': obs['expiry_utc'], 'exit_close': exit_price,
                   'settlement_source_sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
                   'results': results, 'broker_orders': 0, 'research_only': True}
        _new_file(dest, _envelope('ATR_SETTLEMENT', payload))
        made.append({'observation': obsfile.name, 'results': results})
    return made


def report(*, journal=JOURNAL, payout=0.8):
    if not 0 < payout <= 1:
        raise ValueError('Invalid payout')
    base = Path(journal)
    counts = {name: dict.fromkeys(('WIN', 'LOSS', 'PUSH', 'ABSTAINED'), 0)
              for name in ('control_025', 'challenger_050')}
    records = list(sorted((base / 'observations').glob('*.json')))
    observed = set()
    for obsfile in records:
        obs = _load_envelope(obsfile, 'ATR_PAIR')
        if obsfile.name in observed:
            raise ValueError('Duplicate observation')
        observed.add(obsfile.name)
        if set(obs['models']) != set(counts):
            raise ValueError('Missing paired arm')
        dest = base / 'settlements' / obsfile.name
        if not dest.exists(): continue
        settled = _load_envelope(dest, 'ATR_SETTLEMENT')
        if settled['observation_sha256'] != digest(obs):
            raise ValueError('Settlement does not match observation')
        if utc(settled['observed_utc']) < utc(obs['expiry_utc']):
            raise ValueError('Settlement prematurely observed')
        for name in counts:
            outcome = settled['results'][name]
            if outcome not in counts[name]: raise ValueError('Bad outcome')
            counts[name][outcome] += 1
    score = {}
    for name, outcomes in counts.items():
        n = outcomes['WIN'] + outcomes['LOSS']
        score[name] = {'counts': outcomes, 'resolved_directional': n,
                       'win_rate': outcomes['WIN']/n if n else None,
                       'hypothetical_net_units': round(outcomes['WIN']*payout - outcomes['LOSS'], 6)}
    return {'pairs_recorded': len(records), 'pairs_settled': sum((base/'settlements'/p.name).exists() for p in records),
            'arms': score, 'payout': payout, 'break_even': 1/(1+payout),
            'comparison_status': 'INSUFFICIENT_INDEPENDENT_EVIDENCE' if min(x['resolved_directional'] for x in score.values()) < 100 else 'DESCRIPTIVE_ONLY_REQUIRES_INDEPENDENT_VALIDATION',
            'not_broker_verified': True, 'trading_signal': 'NO TRADE', 'api_requests': 0, 'broker_orders': 0}


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--captures', default=str(CAPTURES))
    p.add_argument('--journal', default=str(JOURNAL))
    p.add_argument('--record-current', action='store_true', help='Only if saved capture really was created in last 180 seconds')
    args = p.parse_args(argv)
    captures = sorted(Path(args.captures).glob('*.csv'))
    if not captures:
        print('NO_SAVED_CAPTURES'); return 2
    newly = []
    # Only settle with archived captures that have an exact entry AND expiry bar.
    for path in captures:
        newly.extend(settle(path, journal=args.journal))
    print('NEW_PAIRED_SETTLEMENTS:', len(newly))
    if args.record_current:
        try:
            file, obs = record(captures[-1], journal=args.journal)
            print('PAIRED_OBSERVATION:', file)
            print('RESEARCH_SIGNALS:', obs['models'])
        except (ValueError, FileExistsError) as err:
            print('NO_NEW_OBSERVATION:', str(err))
    summary = report(journal=args.journal)
    print('PAIRS_RECORDED:', summary['pairs_recorded'])
    print('PAIRS_SETTLED:', summary['pairs_settled'])
    for name, values in summary['arms'].items():
        print(name, values)
    print('COMPARISON_STATUS:', summary['comparison_status'])
    print('ZERO_HTTP / NO_BROKER_ORDERS / LIVE_SIGNAL: NO TRADE')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
