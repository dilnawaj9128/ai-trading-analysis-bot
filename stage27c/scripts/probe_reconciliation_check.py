"""Stage 27C: safe offline manual-reconciliation checklist.

This command ONLY reads files. It never contacts Twelve Data, mutates evidence,
changes request authorization or approves retry. For uncertain network outcomes,
local timestamps and account-level credit totals do not identify the request.

Run: python scripts/probe_reconciliation_check.py
"""
import argparse
from datetime import datetime, timedelta, timezone
from pathlib import Path

from scripts.probe_recovery_report import inspect


DEFAULT_PROBE = Path('data/api_usage/approved_research_probe.json')
DEFAULT_CSV = Path('data/real_market/latest_eurusd_completed.csv')


def _file_info(path, attempt_time):
    """Return only timestamp evidence; never display file contents or secrets."""
    try:
        if path.is_symlink() or not path.is_file():
            return {'status': 'UNAVAILABLE'}
        modified = datetime.fromtimestamp(path.stat().st_mtime, timezone.utc)
        return {
            'status': 'PRESENT',
            'modified_utc': modified.isoformat(),
            'modified_after_attempt': modified >= attempt_time,
        }
    except (OSError, ValueError, OverflowError):
        return {'status': 'UNAVAILABLE'}


def create_checklist(*, probe_path=DEFAULT_PROBE, csv_path=DEFAULT_CSV,
                     provider_path=None):
    """Compute a non-authorizing review artifact from local immutable observations."""
    probe_path, csv_path = Path(probe_path), Path(csv_path)
    # Does not imply provider-side reconciliation or permission to retry.
    report = inspect(probe_path=probe_path, csv_path=csv_path,
                     provider_path=provider_path)
    result = {
        'stage': '27C',
        'probe_status': report['status'],
        'request_allowed': False,
        'reconciled': False,
        'manual_review_required': True,
        'reason': report.get('reason', 'Insufficient local evidence'),
    }
    started_iso = report.get('started_at_utc')
    if not started_iso:
        result['next_action'] = 'Inspect local probe history integrity before any further action.'
        return result
    try:
        started = datetime.fromisoformat(started_iso)
        if started.tzinfo is None:
            raise ValueError('UTC timezone missing')
        started = started.astimezone(timezone.utc)
    except (ValueError, TypeError):
        result['next_action'] = 'Invalid timestamp: inspect local evidence; keep requests blocked.'
        return result
    result['attempt_started_utc'] = started.isoformat()
    result['review_window_utc'] = (
        (started - timedelta(minutes=5)).isoformat(),
        (started + timedelta(minutes=10)).isoformat(),
    )
    result['failure_category'] = report.get('failure_category', 'NOT_RECORDED')
    result['attempt_count'] = report.get('attempt_count', 0)
    result['csv_evidence'] = _file_info(csv_path, started)
    result['provider_snapshot_evidence'] = (
        _file_info(Path(provider_path), started) if provider_path is not None
        else {'status': 'NOT_CHECKED'}
    )
    if report['status'] == 'UNCERTAIN':
        result['next_action'] = (
            'Review the Twelve Data account usage/credits for the UTC window; '
            'record any provider support response and compare with local request '
            'evidence. Account-level credits or file timestamps alone cannot '
            'identify this request. Keep automatic requests blocked.'
        )
    elif report['status'] == 'VERIFIED':
        result['next_action'] = (
            'Last probe is VERIFIED; use existing normal cooldown and budget '
            'guards. This report grants no additional authorization.'
        )
    else:
        result['next_action'] = 'Review unfinished request evidence; no automatic retry.'
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--probe', type=Path, default=DEFAULT_PROBE)
    parser.add_argument('--csv', type=Path, default=DEFAULT_CSV)
    parser.add_argument('--provider-snapshot', type=Path)
    args = parser.parse_args(argv)
    if args.provider_snapshot is None:
        try:
            from market_data.provider_credit_state import DEFAULT_PATH
            provider_path = DEFAULT_PATH
        except ImportError:
            provider_path = Path('data/api_usage/provider_credits.json')
    else:
        provider_path = args.provider_snapshot
    result = create_checklist(probe_path=args.probe, csv_path=args.csv,
                              provider_path=provider_path)
    print('=== STAGE 27C OFFLINE RECONCILIATION CHECKLIST ===')
    for key, value in result.items():
        if key.endswith('_evidence'):
            print(key + ':')
            for field, val in value.items():
                print('  ' + field + ': ' + str(val))
        else:
            print(f'{key}: {value}')
    print('No network calls. No state changes. No retry authorization.')


if __name__ == '__main__':
    main()
