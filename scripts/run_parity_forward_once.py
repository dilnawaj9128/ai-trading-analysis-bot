"""One-shot, analysis-only broker candle comparison + forward campaign.

A close-price match is not authenticated feed provenance, executable quote parity
or evidence of a profitable prediction strategy. No automated order or polling.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path


def compare_broker_csv(broker_csv=None, journal='data/research/prospective_accuracy', tolerance=0.00005, minimum_matches=30):
    result = {'status': 'NO_BROKER_CSV', 'quotex_parity_verified': False,
              'broker_feed_authenticated': False, 'executable_quote_parity_verified': False,
              'matching_minutes': 0, 'tolerance': tolerance,
              'reason': 'No independently obtained Quotex 1-minute UTC OHLC CSV supplied.'}
    if not broker_csv:
        return result
    captures = sorted((Path(journal) / 'captures').glob('*.csv'))
    if not captures:
        return dict(result, status='NO_PROVIDER_CAPTURE', reason='No saved Twelve Data capture.')
    from research.stage29_backtest import load_candles
    from research.real_prediction_campaign import _candles
    broker = load_candles(broker_csv)
    matching = {}
    for capture in captures:
        _, df, _ = _candles(capture)
        for row in df.itertuples(index=False):
            t = row.timestamp
            vals = tuple(float(getattr(row, k)) for k in ('Open','High','Low','Close'))
            if t in matching and matching[t] != vals:
                return dict(result, status='PROVIDER_CAPTURE_CONFLICT', reason='Saved provider captures disagree at the same minute.')
            matching[t] = vals
    overlap = []
    for row in broker.itertuples(index=False):
        provider = matching.get(row.timestamp)
        if provider:
            broker_vals = tuple(float(getattr(row, k)) for k in ('Open','High','Low','Close'))
            overlap.append(max(abs(a-b) for a,b in zip(provider, broker_vals)))
    result['matching_minutes'] = len(overlap)
    result['broker_csv_sha256'] = hashlib.sha256(Path(broker_csv).read_bytes()).hexdigest()
    if not overlap:
        return dict(result, status='NO_MATCHING_UTC_MINUTES', reason='Timestamps do not overlap. Check UTC timestamps and candle-open convention.')
    result['max_abs_ohlc_difference'] = max(overlap)
    result['mean_max_ohlc_difference'] = sum(overlap)/len(overlap)
    result['minutes_within_tolerance'] = sum(x <= tolerance for x in overlap)
    if len(overlap) < minimum_matches:
        result['status'] = 'INSUFFICIENT_OVERLAP'
        result['reason'] = f'At least {minimum_matches} matching one-minute candles required for descriptive comparison.'
    elif max(overlap) > tolerance:
        result['status'] = 'PRICE_MISMATCH'
        result['reason'] = 'At least one matching OHLC candle differs beyond tolerance.'
    else:
        result['status'] = 'CANDLE_CLOSE_MATCH_DESCRIPTIVE_ONLY'
        result['reason'] = 'Saved candle values match within tolerance; broker-feed provenance and executable payout/latency remain unverified.'
    return result


def run(*, broker_csv=None, approved=False, journal='data/research/prospective_accuracy', report_dir='data/research/real_accuracy_campaign'):
    from scripts.run_three_accuracy_tasks import run as run_existing
    from research.real_prediction_campaign import preflight_observation_window
    # One-shot preflight is advisory; authoritative authorization remains inside existing live runner.
    preflight = preflight_observation_window(journal)
    campaign = run_existing(journal=journal, report_dir=report_dir, approved=approved)
    parity = compare_broker_csv(broker_csv, journal)
    scoring = campaign['task_3_accuracy']
    result = {'schema': 1, 'generated_at_utc': datetime.now(timezone.utc).isoformat(),
              'broker_comparison': parity, 'pre_fetch_nonoverlap_preflight': preflight,
              'forward_status': campaign['task_2_forward_testing'],
              'forward_accuracy': scoring, 'directional_predictions_scored': scoring['resolved_directional'],
              'research_only': True, 'live_signal': 'NO TRADE', 'broker_orders': 0,
              'forecast_skill_verified': False,
              'caution': 'A saved-file OHLC comparison is not proof of Quotex parity; directional accuracy requires prospective UP/DOWN outcomes.'}
    dest = Path(report_dir) / 'latest_broker_parity_and_forward.json'
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(result, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    return result, str(dest)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--broker-csv', help='Independently exported Quotex EUR/USD 1min CSV with timestamp,Open,High,Low,Close and explicit UTC offsets')
    p.add_argument('--approve-up-to-two-requests', action='store_true', help='Explicitly approve existing guarded Twelve Data fetch; may spend up to two accounted credits')
    args = p.parse_args()
    output, path = run(broker_csv=args.broker_csv, approved=args.approve_up_to_two_requests)
    print('BROKER_COMPARISON:', output['broker_comparison']['status'])
    print('QUOTEX_PARITY_VERIFIED:', False)
    print('LIVE_STATUS:', output['forward_status']['live_status'])
    print('PENDING:', output['forward_status']['pending'])
    print('COUNTS:', output['forward_accuracy']['counts'])
    print('DIRECTIONAL_SCORED:', output['directional_predictions_scored'])
    print('FORWARD_WIN_RATE:', output['forward_accuracy']['win_rate'])
    print('STATISTICAL_STATUS:', output['forward_accuracy']['statistical_status'])
    print('REPORT:', path)
    print('NO BROKER ORDERS / NO ACCURACY CERTIFICATION')

if __name__ == '__main__':
    main()
