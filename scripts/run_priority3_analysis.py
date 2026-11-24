"""Stage 3 offline analysis of the *attested* Stage 52D EUR/USD snapshot.

Zero HTTP, API credits, broker access, trading orders, or mutation of source files.
All directional outputs remain NO TRADE when broker/provider feed mode is unknown.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from market_data.recovery_verified_gate import verified_recovery_override


def run_priority3(*, root=Path('data'), now=None, analyzer=None):
    root = Path(root)
    old_probe = root / 'api_usage' / 'approved_research_probe.json'
    recovery = root / 'api_usage' / 'stage52d_new_recovery_probe.json'
    csv = root / 'real_market' / 'stage52d_new_completed.csv'

    # Verify full immutable chain: original UNCERTAIN case, authorization,
    # verified response, reservation ledger, and exact SHA-256 of saved CSV.
    if verified_recovery_override(old_probe) is not True:
        raise ValueError('Recovery attestation FAILED: refusing unverified CSV')
    evidence = json.loads(recovery.read_text(encoding='utf-8'))
    if evidence.get('status') != 'VERIFIED' or evidence.get('checkpoint') != 'VERIFIED':
        raise ValueError('Recovery is not verified')
    if Path(evidence['csv_path']).resolve() != csv.resolve():
        raise ValueError('Recovery CSV path mismatch')

    if analyzer is None:
        # Import lazily: never require the analysis engine for pure attestation tests.
        from scripts.analyze_saved_real_candles import analyze
        analyzer = analyze
    current_time = now or datetime.now(timezone.utc)
    if current_time.tzinfo is None or current_time.utcoffset() is None:
        raise ValueError('Timezone-aware clock required')
    report = analyzer(csv, now=current_time)
    if not isinstance(report, dict):
        raise ValueError('Invalid analysis report')
    if report.get('analysis_only') is not True or report.get('execution_enabled') is not False:
        raise ValueError('Unsafe research report')
    if report.get('symbol') != 'EUR/USD' or report.get('timeframe') != '1min':
        raise ValueError('Research profile mismatch')
    if report.get('expiry_minutes') != 15:
        raise ValueError('Research expiry mismatch')
    if report.get('candles') != evidence['candles']:
        raise ValueError('Candle count mismatch')
    # A Twelve Data quote is not an authenticated Quotex broker quote. The
    # research signal must remain NO TRADE until feed verification is designed.
    if report.get('feed_mode') != 'unverified':
        raise ValueError('Unexpected feed verification claim')
    if report.get('signal') != 'NO TRADE':
        raise ValueError('Unverified feed cannot produce actionable directions')

    return {
        'stage': 'PRIORITY_3_OFFLINE_ANALYSIS',
        'source_attested': True,
        'source_request_id': evidence['request_id'],
        'source_csv_sha256': evidence['csv_sha256'],
        **report,
        'research_only': True,
        'broker_execution': False,
        'http_requests': 0,
        'api_credits_used': 0,
        'warning': 'Unverified broker/feed timing: NO TRADE. No predictive-accuracy claim.',
    }


def main():
    parser = argparse.ArgumentParser(description='Attested offline EUR/USD analysis; ZERO API calls')
    parser.add_argument('--data-root', type=Path, default=Path('data'))
    args = parser.parse_args()
    try:
        report = run_priority3(root=args.data_root)
    except (ValueError, OSError, KeyError, ImportError, TypeError) as exc:
        print('PRIORITY_3_BLOCKED:', type(exc).__name__, str(exc))
        raise SystemExit(1)
    print(json.dumps(report, indent=2, default=str))


if __name__ == '__main__':
    main()
