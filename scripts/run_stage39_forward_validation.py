"""Stage 39 prospective observation protocol; offline, no orders or HTTP.

Pre-register research plan before observing any future candles. Every observation
is independently gated by Stage 33 attestation. Records cannot be promoted to
wins by this script. Local journal is not tamper-proof or broker-certified.
"""
import argparse
import fcntl
import hashlib
import json
import os
import tempfile
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_RUN = Path('data/forward_testing/stage39_run.json')
DEFAULT_CSV = Path('data/real_market/latest_eurusd_completed.csv')
DEFAULT_PROBE = Path('data/api_usage/approved_research_probe.json')


def utc_now():
    return datetime.now(timezone.utc)


def parse_time(value):
    t = datetime.fromisoformat(value)
    if t.tzinfo is None:
        raise ValueError('Timezone-aware timestamp required')
    return t.astimezone(timezone.utc)


def atomic_json(path, data):
    temp = None
    try:
        with tempfile.NamedTemporaryFile('w', encoding='utf8', dir=path.parent,
                                         prefix='.stage39_', delete=False) as out:
            temp = Path(out.name)
            os.fchmod(out.fileno(), 0o600)
            json.dump(data, out, indent=2, sort_keys=True)
            out.flush()
            os.fsync(out.fileno())
        os.replace(temp, path)
    finally:
        if temp is not None:
            temp.unlink(missing_ok=True)


@contextmanager
def locked(path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.with_name(path.name + '.lock').open('a+b') as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield path
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def freeze(path=DEFAULT_RUN, *, now=None):
    """One immutable research plan; never overwrite an existing run."""
    now = now or utc_now()
    if now.tzinfo is None:
        raise ValueError('Timezone-aware freeze time required')
    with locked(path) as path:
        if path.exists():
            raise ValueError('Run already exists; never overwrite a frozen plan')
        run = {
            'version': 1, 'frozen_at_utc': now.astimezone(timezone.utc).isoformat(),
            'strategy': 'rsi', 'strategy_status': 'UNVALIDATED_RESEARCH',
            'symbol': 'EUR/USD', 'timeframe': '1min', 'expiry_minutes': 15,
            'payout_assumption': 0.8, 'minimum_resolved': 100,
            'analysis_only': True, 'execution_enabled': False,
            'observations': [],
        }
        atomic_json(path, run)
    return run


def load_run(path):
    run = json.loads(Path(path).read_text(encoding='utf8'))
    if (type(run) is not dict or run.get('version') != 1
            or run.get('strategy_status') != 'UNVALIDATED_RESEARCH'
            or run.get('analysis_only') is not True
            or run.get('execution_enabled') is not False
            or not isinstance(run.get('observations'), list)):
        raise ValueError('Invalid or altered research run')
    parse_time(run['frozen_at_utc'])
    return run


def observe(path=DEFAULT_RUN, *, csv=DEFAULT_CSV, probe=DEFAULT_PROBE,
            now=None, evaluator=None):
    """Only read local evidence; record one observation without settling it."""
    now = now or utc_now()
    if now.tzinfo is None:
        raise ValueError('Timezone-aware observation required')
    now = now.astimezone(timezone.utc)
    if evaluator is None:
        from research.stage33_provider_attestation import evaluate_attested_snapshot
        evaluator = evaluate_attested_snapshot
    with locked(path) as path:
        run = load_run(path)
        if now <= parse_time(run['frozen_at_utc']):
            raise ValueError('Observation must be strictly after strategy freeze')
        previous = run['observations']
        if previous and now <= parse_time(previous[-1]['observed_at_utc']):
            raise ValueError('Observations must be strictly chronological')
        result = evaluator(csv, probe, observed_at=now)
        if (type(result) is not dict or result.get('status') not in ('VALID', 'BLOCKED')
                or result.get('signal') not in ('UP', 'DOWN', 'NO TRADE')):
            raise ValueError('Invalid attestation assessment')
        if result['status'] == 'BLOCKED' and result['signal'] != 'NO TRADE':
            raise ValueError('Blocked observation cannot have direction')
        # A standalone CSV alone is never trusted.
        if result.get('provider_attested') is not True and result['status'] == 'VALID':
            raise ValueError('Cannot accept direction without provider evidence')
        csv_path = Path(csv)
        digest = hashlib.sha256(csv_path.read_bytes()).hexdigest() if csv_path.is_file() else None
        item = {
            'observed_at_utc': now.isoformat(), 'csv_sha256': digest,
            'status': result['status'], 'signal': result['signal'],
            'reason': str(result.get('reason', ''))[:200],
            'provider_attested': result.get('provider_attested') is True,
            'outcome': 'NOT_EVALUATED', 'analysis_only': True,
            'execution_enabled': False,
        }
        if previous and digest is not None and digest == previous[-1]['csv_sha256']:
            raise ValueError('Identical CSV snapshot already observed; no replay')
        previous.append(item)
        atomic_json(path, run)
        return item


def report(path=DEFAULT_RUN):
    run = load_run(path)
    rows = run['observations']
    blocked = sum(row['status'] == 'BLOCKED' for row in rows)
    directional = sum(row['status'] == 'VALID' and row['signal'] in ('UP', 'DOWN') for row in rows)
    return {
        'frozen_at_utc': run['frozen_at_utc'], 'strategy': run['strategy'],
        'strategy_status': run['strategy_status'], 'observations': len(rows),
        'blocked': blocked, 'directional': directional,
        'settled': 0, 'win_rate': None,
        'verdict': 'INSUFFICIENT: independent verified settlements not available',
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('freeze', 'observe', 'report'))
    parser.add_argument('--run', type=Path, default=DEFAULT_RUN)
    parser.add_argument('--csv', type=Path, default=DEFAULT_CSV)
    parser.add_argument('--probe', type=Path, default=DEFAULT_PROBE)
    args = parser.parse_args()
    try:
        if args.action == 'freeze':
            result = freeze(args.run)
        elif args.action == 'observe':
            result = observe(args.run, csv=args.csv, probe=args.probe)
        else:
            result = report(args.run)
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        parser.exit(1, f'BLOCKED: {type(exc).__name__}: {exc}\n')
    print('STAGE 39 PROSPECTIVE VALIDATION — OFFLINE / NO ORDERS')
    print(json.dumps(result, indent=2, sort_keys=True))
    print('No API calls, no broker parity claims, no automatic settlement.')


if __name__ == '__main__':
    main()
