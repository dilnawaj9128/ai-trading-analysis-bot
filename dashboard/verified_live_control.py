"""Explicit, one-shot Streamlit bridge to the existing audited live fetch.

Does not bypass provider credit guards, replay uncertain attempts, launch a
background timer, or perform trading operations. One button click may approve
at most two Twelve Data requests (credit renewal and normal candle fetch).
"""
from __future__ import annotations

import os
from pathlib import Path


def approved_live_snapshot(*, approved: bool, api_key: str | None = None,
                           runner=None, env_path: str | Path = '.env') -> dict:
    if approved is not True:
        raise ValueError('Explicit one-shot approval required')
    if api_key is None:
        # python-dotenv needs an explicit file path when invoked from stdin,
        # and Streamlit should not expose the secret in its interface.
        from dotenv import load_dotenv
        load_dotenv(dotenv_path=Path(env_path), override=False)
        api_key = os.environ.get('TWELVE_DATA_API_KEY')
    if not api_key or not api_key.strip():
        raise ValueError('TWELVE_DATA_API_KEY is not configured')
    runner_is_default = runner is None
    if runner_is_default:
        from scripts.run_one_normal_fetch import fetch_one_research_snapshot
        runner = fetch_one_research_snapshot
    result = runner(approved=True, api_key=api_key, include_analysis=True,
                    **({'reconcile_verified': True} if runner_is_default else {}))
    if not isinstance(result, dict) or result.get('status') != 'VERIFIED_NORMAL_FETCH':
        raise ValueError('Normal fetch was not verified')
    analysis = result.get('analysis')
    if (not isinstance(analysis, dict)
            or analysis.get('status') != 'RESEARCH_ANALYSIS_READY'
            or analysis.get('symbol') != 'EUR/USD'
            or analysis.get('timeframe') != '1min'
            or analysis.get('expiry_minutes') != 15
            or analysis.get('signal') != 'NO TRADE'
            or analysis.get('execution_enabled') is not False
            or analysis.get('broker_orders') != 0
            or analysis.get('extra_http_requests') != 0):
        raise ValueError('Unsafe or incomplete research analysis')
    return {
        'status': 'VERIFIED_NORMAL_FETCH',
        'candles': result['candles'],
        'credits_renewed': result['credits_renewed'] is True,
        'analysis': analysis,
        'analysis_only': True,
        'maximum_http_requests': 2,
    }
