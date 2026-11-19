"""Read-only, offline report for the last Twelve Data research probe attempt.

Never sends requests, writes state, settles claims, or authorizes retries.
Run: python scripts/probe_recovery_report.py
"""
import json
from datetime import datetime, timezone
from pathlib import Path

PROBE = Path('data/api_usage/approved_research_probe.json')
CSV = Path('data/real_market/latest_eurusd_completed.csv')


def _safe_read(path):
    """Treat unreadable/corrupt/unexpected history as blocked."""
    try:
        if path.is_symlink() or not path.is_file():
            return None
        history = json.loads(path.read_text(encoding='utf-8'))
        if type(history) is not dict or history.get('version') != 1:
            return None
        attempts = history.get('attempts')
        if type(attempts) is not list:
            return None
        return attempts
    except (OSError, ValueError, TypeError):
        return None


def inspect(*, probe_path=PROBE, csv_path=CSV, provider_path=None):
    """Inspect local evidence without changing it; return safe, non-secret fields."""
    probe_path, csv_path = Path(probe_path), Path(csv_path)
    attempts = _safe_read(probe_path)
    if attempts is None:
        return {'status': 'BLOCKED', 'reason': 'Probe history missing or unreadable',
                'reconciled': False, 'request_allowed': False}
    if not attempts:
        return {'status': 'NO_ATTEMPTS', 'reconciled': False,
                'request_allowed': False, 'reason': 'No attempt evidence to reconcile'}
    entry = attempts[-1]
    if type(entry) is not dict or entry.get('status') not in {
            'INTENT', 'BUDGET_RESERVED', 'REQUEST_ATTEMPTED', 'VERIFIED', 'UNCERTAIN'}:
        return {'status': 'BLOCKED', 'reason': 'Invalid last attempt evidence',
                'reconciled': False, 'request_allowed': False}
    try:
        started = datetime.fromisoformat(entry['started_at'])
        if started.tzinfo is None:
            raise ValueError('Timezone missing')
        started = started.astimezone(timezone.utc)
    except (ValueError, KeyError, TypeError):
        return {'status': 'BLOCKED', 'reason': 'Invalid attempt timestamp',
                'reconciled': False, 'request_allowed': False}
    provider_path = Path(provider_path) if provider_path is not None else None
    result = {'status': entry['status'], 'started_at_utc': started.isoformat(),
              'attempt_count': len(attempts), 'failure_category': entry.get('failure_category', 'NOT_RECORDED'),
              'reconciled': False, 'request_allowed': False}
    for label, path in [('csv', csv_path), ('provider_snapshot', provider_path)]:
        if path is None:
            result[label + '_modified_after_attempt'] = 'NOT_CHECKED'
            continue
        try:
            if path.is_symlink():
                raise OSError('Symlink')
            mtime = datetime.fromtimestamp(path.stat().st_mtime, timezone.utc)
            result[label + '_modified_after_attempt'] = mtime >= started
        except (OSError, ValueError, OverflowError):
            result[label + '_modified_after_attempt'] = 'MISSING_OR_UNREADABLE'
    if entry['status'] == 'UNCERTAIN':
        result['reason'] = ('Unresolved attempt. Local file timestamps cannot prove '
                            'provider-side outcome or API-credit use. Manual reconciliation required.')
    elif entry['status'] == 'VERIFIED':
        result['reason'] = ('Last attempt marked VERIFIED. This report does not authorize '
                            'new requests; normal probe guards still apply.')
    else:
        result['reason'] = 'Attempt unfinished: manual review required.'
    return result


def main():
    # Provider path imported only here, to keep inspect() easy to test offline.
    try:
        from market_data.provider_credit_state import DEFAULT_PATH
    except ImportError:
        DEFAULT_PATH = Path('data/api_usage/provider_credits.json')
    result = inspect(provider_path=DEFAULT_PATH)
    print('=== STAGE 27B OFFLINE RECOVERY REPORT ===')
    for key, value in result.items():
        print(f'{key}: {value}')
    print('No HTTP requests. No files changed. No automatic reconciliation or retry.')


if __name__ == '__main__':
    main()
