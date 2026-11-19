"""One explicitly approved Twelve Data research fetch.

Purpose: independently validate real completed candles when the provider credit
snapshot is stale. Never changes existing authorization journal/ledger, never
settles earlier uncertain requests, never trades, never retries automatically.
"""
import argparse
import hashlib
import fcntl
import json
import os
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path

import requests

from config.market_config import create_research_config
from market_data import twelve_data_client as td
from market_data.credit_response_handler import refresh_credits_from_response
from market_data.provider_credit_state import DEFAULT_PATH

STATE = Path('data/api_usage/approved_research_probe.json')
DEST = Path('data/real_market/latest_eurusd_completed.csv')
COOLDOWN_SECONDS = 180
CONNECT_TIMEOUT_SECONDS = 5
READ_TIMEOUT_SECONDS = 30

class ProbeBlocked(RuntimeError):
    pass


def _utc():
    return datetime.now(timezone.utc)


def _atomic_write(path, data):
    temp = None
    try:
        with tempfile.NamedTemporaryFile('w', encoding='utf-8', dir=path.parent,
                                         prefix='.probe_', delete=False) as handle:
            temp = Path(handle.name)
            os.fchmod(handle.fileno(), 0o600)
            json.dump(data, handle, sort_keys=True)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp, path)
        fd = os.open(path.parent, os.O_RDONLY)
        try: os.fsync(fd)
        finally: os.close(fd)
    finally:
        if temp is not None:
            temp.unlink(missing_ok=True)


def _load(path):
    if not path.exists():
        return {'version': 1, 'attempts': []}
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError) as exc:
        raise ProbeBlocked('Probe history unreadable: manual review required') from exc
    if (type(data) is not dict or data.get('version') != 1
            or type(data.get('attempts')) is not list):
        raise ProbeBlocked('Invalid probe history')
    for attempt in data['attempts']:
        if (type(attempt) is not dict or attempt.get('status') not in
                {'INTENT', 'BUDGET_RESERVED', 'REQUEST_ATTEMPTED', 'VERIFIED', 'UNCERTAIN'}
                or not isinstance(attempt.get('started_at'), str)):
            raise ProbeBlocked('Invalid probe evidence')
    return data


def probe_once(*, approved, api_key=None, state_path=STATE,
               budget_path=td.STATE_PATH, provider_path=DEFAULT_PATH,
               csv_path=DEST, session=None, now=None):
    """Exactly one approved network request; mocks may inject session for tests."""
    if approved is not True:
        raise ProbeBlocked('Explicit approval required for one real API request')
    key = api_key if api_key is not None else os.environ.get('TWELVE_DATA_API_KEY')
    if not key:
        raise ProbeBlocked('TWELVE_DATA_API_KEY missing')
    now = now or _utc()
    if now.tzinfo is None:
        raise ProbeBlocked('Timezone-aware time required')
    now = now.astimezone(timezone.utc)
    state_path, budget_path, provider_path, csv_path = map(
        Path, (state_path, budget_path, provider_path, csv_path))
    lock_path = state_path.with_name(state_path.name + '.lock')
    all_paths = [state_path, lock_path, budget_path, provider_path, csv_path]
    if len({p.resolve() for p in all_paths}) != len(all_paths):
        raise ProbeBlocked('Overlapping paths')
    state_path.parent.mkdir(parents=True, exist_ok=True)

    with lock_path.open('a+b') as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        try:
            a = os.fstat(lock.fileno()); b = os.stat(lock_path)
            if a.st_ino != b.st_ino or a.st_dev != b.st_dev:
                raise ProbeBlocked('Probe lock changed')
            history = _load(state_path)
            if history['attempts']:
                previous = history['attempts'][-1]
                if previous['status'] != 'VERIFIED':
                    raise ProbeBlocked('Previous probe unresolved; no retry')
                try:
                    previous_time = datetime.fromisoformat(previous['started_at'])
                except ValueError as exc:
                    raise ProbeBlocked('Invalid previous timestamp') from exc
                if previous_time.tzinfo is None or now < previous_time:
                    raise ProbeBlocked('Invalid clock chronology')
                if (now - previous_time).total_seconds() < COOLDOWN_SECONDS:
                    raise ProbeBlocked('Three-minute research cooldown active')

            # Stage 28: reserve budget BEFORE appending an attempt. Budget
            # rejection means no HTTP was attempted and must not poison the
            # durable probe journal with a false UNCERTAIN status. Keep the
            # probe lock throughout and still journal BEFORE network I/O.
            td.reserve_request(path=budget_path, now=now)
            attempt = {'id': uuid.uuid4().hex, 'started_at': now.isoformat(),
                       'status': 'INTENT'}
            history['attempts'].append(attempt)
            _atomic_write(state_path, history)
            try:
                attempt['status'] = 'BUDGET_RESERVED'
                _atomic_write(state_path, history)
                attempt['status'] = 'REQUEST_ATTEMPTED'
                _atomic_write(state_path, history)
                client = session if session is not None else requests
                response = client.get(
                    td.API_URL,
                    params={'apikey': key, 'symbol': 'EUR/USD',
                            'interval': '1min', 'outputsize': 120,
                            'timezone': 'UTC', 'format': 'JSON'},
                    timeout=(CONNECT_TIMEOUT_SECONDS, READ_TIMEOUT_SECONDS), allow_redirects=False,
                )
                response.raise_for_status()
                if response.status_code != 200:
                    raise ValueError('Unexpected provider response status')
                payload = response.json()
                config = create_research_config('quotex', 'forex', 'EUR/USD', '1min', 15)
                parsed = td.parse_candles(payload, config, now=_utc())
                snapshot = refresh_credits_from_response(
                    response, path=provider_path, now=_utc())
                if snapshot.updated is not True:
                    raise ValueError('Provider credit headers unavailable')
                # Save validated completed candles only. A crash after response
                # verification still leaves journal unresolved until this completes.
                csv_path.parent.mkdir(parents=True, exist_ok=True)
                temp = csv_path.with_name('.' + csv_path.name + '.' + uuid.uuid4().hex + '.tmp')
                try:
                    parsed['frame'].to_csv(temp, index=False)
                    os.replace(temp, csv_path)
                finally:
                    temp.unlink(missing_ok=True)
                # Bind the exact persisted CSV bytes to this validated request.
                # Older journal records without this evidence remain untrusted.
                attempt['csv_sha256'] = hashlib.sha256(csv_path.read_bytes()).hexdigest()
                attempt['csv_path'] = str(csv_path.resolve())
                attempt['provider'] = 'twelve_data'
                attempt['symbol'] = 'EUR/USD'
                attempt['timeframe'] = '1min'
                attempt['candles'] = parsed['candles']
                attempt['verified_at_utc'] = _utc().isoformat()
                attempt['status'] = 'VERIFIED'
                _atomic_write(state_path, history)
                return {'status': 'VERIFIED', 'candles': parsed['candles'],
                        'latest_utc': parsed['latest_utc'], 'stale': parsed['stale'],
                        'credits_left': snapshot.credits_left,
                        'csv_path': str(csv_path), 'analysis_only': True,
                        'execution_enabled': False}
            except BaseException as exc:
                if attempt['status'] != 'VERIFIED':
                    # Store only a safe exception category, never exception text:
                    # Requests errors can contain query strings and API keys.
                    if isinstance(exc, requests.exceptions.ConnectTimeout):
                        category = 'CONNECT_TIMEOUT'
                    elif isinstance(exc, requests.exceptions.ReadTimeout):
                        category = 'READ_TIMEOUT'
                    elif isinstance(exc, requests.exceptions.Timeout):
                        category = 'TIMEOUT'
                    elif isinstance(exc, requests.exceptions.RequestException):
                        category = 'HTTP_ERROR'
                    else:
                        category = 'LOCAL_OR_RESPONSE_ERROR'
                    attempt['status'] = 'UNCERTAIN'
                    attempt['failure_category'] = category
                    attempt['last_failure_at'] = _utc().isoformat()
                    _atomic_write(state_path, history)
                raise
        finally:
            fcntl.flock(lock.fileno(), fcntl.LOCK_UN)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--approve-one-request', action='store_true',
                        help='Authorize one real Twelve Data request; may use 1 API credit')
    args = parser.parse_args()
    try:
        result = probe_once(approved=args.approve_one_request)
    except (ProbeBlocked, Exception) as exc:
        # Do not print request/response content or API keys.
        # Requests exception strings can include the URL and its apikey.
        print(f'BLOCKED / FAILED: {type(exc).__name__}. Check local logs privately; no automatic retry.')
        raise SystemExit(1)
    for field in ('status', 'candles', 'latest_utc', 'stale', 'credits_left', 'csv_path'):
        print(f'{field}: {result[field]}')
    print('RESEARCH ONLY. Broker feed parity and prediction accuracy unverified.')

if __name__ == '__main__':
    main()
