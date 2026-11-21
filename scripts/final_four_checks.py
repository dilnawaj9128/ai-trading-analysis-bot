#!/usr/bin/env python3
"""Offline, read-only credit/reservation/feed/monitor readiness report.
Never reads .env/API keys; no HTTP or accounting mutations.
"""
import json
from datetime import datetime, timezone
from pathlib import Path


def main():
    from dashboard.twelve_data_readiness import readiness
    from dashboard.credit_renewal_diagnostics import credit_renewal_readiness
    from market_data.unified_request_guard import _load_ledger

    report_dir = Path('reports')
    report_dir.mkdir(exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    provider = Path('data/api_usage/provider_credits.json')
    ledger_path = provider.with_name(provider.name + '.reservations.json')
    r = readiness()
    diagnostic = credit_renewal_readiness()
    pending = []
    problems = []
    try:
        ledger = _load_ledger(ledger_path)
        for request_id, entry in ledger['requests'].items():
            if entry['status'] in ('PENDING', 'UNCERTAIN'):
                pending.append({'request_prefix': request_id[:10], 'status': entry['status'], 'credits': entry['credits']})
    except (OSError, ValueError, KeyError, TypeError) as exc:
        problems.append('Reservation ledger unavailable or invalid: ' + type(exc).__name__)
    local_ready = r['status'] == 'PREFLIGHT_POSSIBLE'
    if not local_ready:
        problems.append('Fresh fetching not authorized by local preflight: ' + r['reason'])
    if pending:
        problems.append(f'{len(pending)} reservations unresolved; receipt-bound evidence required')
    problems.append('Feed mode and Quotex price parity require external independent verification')
    problems.append('Continuous live monitor reliability requires a permitted long-running observation')
    report = {
        'generated_utc': datetime.now(timezone.utc).isoformat(),
        'analysis_only': True, 'http_requests': 0, 'accounting_mutations': 0,
        'provider_credits_last_observed': r['provider_credits_left'],
        'snapshot_fresh': r['snapshot_fresh'], 'snapshot_age_seconds': r['snapshot_age_seconds'],
        'outstanding_reserved': r['outstanding_reserved'],
        'conservative_headroom': r['conservative_headroom'],
        'required_one_fetch_headroom': r['minimum_one_fetch_headroom'],
        'local_fetch_preflight': r['status'], 'renewal_preflight': diagnostic['status'],
        'pending_requests_prefix_only': pending,
        'feed_mode_verified': False, 'quotex_parity_verified': False,
        'live_monitor_sustained_test_verified': False,
        'blocked_reasons': problems,
        'notes': 'Read-only local evidence; only provider-confirmed quota/outcomes can resolve reservations. No credentials collected.'
    }
    destination = report_dir / f'final_four_checks_{stamp}.json'
    destination.write_text(json.dumps(report, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    print('FOUR-CHECK REPORT:', destination)
    for k in ('local_fetch_preflight', 'renewal_preflight', 'outstanding_reserved', 'snapshot_fresh', 'conservative_headroom', 'required_one_fetch_headroom'):
        print(f'{k}: {report[k]}')
    print('PENDING REQUEST PREFIXES:', ', '.join(x['request_prefix'] for x in pending) or '(none)')
    print('NO HTTP / NO ACCOUNTING CHANGES / NO BROKER ORDERS')
    print('100% LIVE READY: NO' if problems else '100% LIVE READY: NOT PROVEN')


if __name__ == '__main__':
    main()
