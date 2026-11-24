"""Stage 55: offline robustness report on real provider candle files.

Safe: NO HTTP requests, broker actions, or strategy changes.
Usage: python -m scripts.run_stage55_robust_validation --csv FILE [--csv FILE]
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from scripts.stage55_statistical_audit import audit_holdout


def build_report(csv_path, *, min_nonpush=100, payout=0.8):
    from scripts.run_real_data_validation import evaluate
    base = evaluate(csv_path, minimum_resolved=min_nonpush, payout=payout)
    audit = None
    if 'stage29' in base:
        audit = audit_holdout(base['stage29']['holdout'],
                              payout=payout, minimum_resolved=min_nonpush)
    base['stage55'] = {
        'status': 'BLOCKED' if not base['quality']['continuous_one_minute_candles'] else
                  'NO_EVIDENCE' if audit is None else audit['status'],
        'statistical_audit': audit,
        'live_signal': 'NO TRADE',
        'broker_feed_parity_verified': False,
        'ready_for_real_trading': False,
        'additional_http_requests': 0,
        'no_orders': True,
        'holdout_is_exploratory': True,
        'gate_note': 'Do not relax NO TRADE based on historical testing; require prospective evaluation and feed verification.',
    }
    return base


def report_path(csv_path, out_dir, sha):
    # Stable unique hash prevents different files sharing a basename from overwriting.
    basename = Path(csv_path).stem
    safe_stem = ''.join(c if c.isalnum() or c in '-_' else '_' for c in basename)[:60] or 'dataset'
    return Path(out_dir) / f'{safe_stem}_{sha[:16]}_stage55.json'


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--csv', required=True, action='append')
    parser.add_argument('--out-dir', default='data/research/stage55')
    parser.add_argument('--minimum-nonpush', type=int, default=100)
    parser.add_argument('--payout', type=float, default=0.8)
    args = parser.parse_args(argv)
    if len(set(map(str, args.csv))) != len(args.csv):
        parser.error('Duplicate input files')
    if args.minimum_nonpush < 30:
        parser.error('--minimum-nonpush must be >=30')
    if not 0 < args.payout <= 1:
        parser.error('--payout must be in (0,1]')
    output = Path(args.out_dir)
    output.mkdir(parents=True, exist_ok=True)
    statuses = []
    for csv in args.csv:
        try:
            report = build_report(csv, min_nonpush=args.minimum_nonpush, payout=args.payout)
        except (OSError, ValueError, TypeError, KeyError, ImportError, AssertionError) as exc:
            print('DATASET BLOCKED:', csv, type(exc).__name__, str(exc))
            statuses.append(False)
            continue
        dest = report_path(csv, output, report['source_sha256'])
        dest.write_text(json.dumps(report, indent=2, sort_keys=True, default=str) + '\n', encoding='utf-8')
        audit = report['stage55']['statistical_audit']
        print('DATASET:', csv)
        print('SHA256:', report['source_sha256'])
        print('CANDLES:', report['quality']['rows'])
        print('HOLDOUT NON-PUSH:', audit['nonpush_outcomes'] if audit else 0)
        print('WIN RATE:', audit['observed_nonpush_win_rate'] if audit else None)
        print('BREAK EVEN:', audit['break_even_nonpush_win_rate_at_payout'] if audit else 1/(1+args.payout))
        print('P-VALUE:', audit['one_sided_exact_pvalue_vs_break_even'] if audit else None)
        print('STAGE55:', report['stage55']['status'])
        print('LIVE SIGNAL: NO TRADE; NO HTTP; NO ORDERS')
        print('REPORT:', dest)
        statuses.append(bool(audit and audit['statistical_screen_passed']))
    # Passing a historical screen still cannot authorize broker trading.
    return 0 if statuses and all(statuses) else 1


if __name__ == '__main__':
    raise SystemExit(main())
