"""Read-only Twelve Data API credit and data-integration readiness.

Never makes an HTTP request, authorizes API calls, modifies ledgers or reads API keys.
This is a conservative UI/diagnostic preview, not the final request guard.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path


def readiness(*, provider_path='data/api_usage/provider_credits.json', now=None,
              maximum_snapshot_age_seconds=300, ledger_loader=None, reserve_credits=None):
    from market_data.basic8_credit_policy import PROVIDER_RESERVE_CREDITS
    from market_data.unified_request_guard import _load_ledger

    output = {
        'status': 'UNKNOWN', 'provider_credits_left': None,
        'outstanding_reserved': None, 'conservative_headroom': None,
        'reserve_credits': PROVIDER_RESERVE_CREDITS if reserve_credits is None else reserve_credits,
        'minimum_one_fetch_headroom': None, 'snapshot_age_seconds': None,
        'snapshot_fresh': False, 'provider_requests': 0,
        'source': 'LOCAL_READ_ONLY', 'authorization_granted': False,
        'reason': 'Accounting evidence unavailable',
    }
    try:
        if type(output['reserve_credits']) is not int or output['reserve_credits'] < 0:
            raise ValueError('Invalid reserve')
        clock = now or datetime.now(timezone.utc)
        if not isinstance(clock, datetime) or clock.tzinfo is None or clock.utcoffset() is None:
            raise ValueError('Aware time required')
        clock = clock.astimezone(timezone.utc)
        provider = Path(provider_path)
        snapshot = json.loads(provider.read_text(encoding='utf-8'))
        if type(snapshot) is not dict or snapshot.get('version') != 1:
            raise ValueError('Invalid snapshot')
        left = snapshot.get('credits_left')
        if type(left) is not int or left < 0:
            raise ValueError('Invalid credit value')
        when = datetime.fromisoformat(snapshot['observed_at'])
        if when.tzinfo is None or when.utcoffset() is None:
            raise ValueError('Non timezone-aware snapshot')
        age = (clock - when.astimezone(timezone.utc)).total_seconds()
        if age < 0:
            raise ValueError('Future-dated snapshot')
        ledger_path = provider.with_name(provider.name + '.reservations.json')
        # If accounting file is missing, do not presume it is safe/empty.
        if not ledger_path.is_file():
            output.update(provider_credits_left=left, snapshot_age_seconds=round(age, 1),
                          reason='Reservation ledger unavailable; no authorization inferred')
            return output
        ledger = (ledger_loader or _load_ledger)(ledger_path)
        reserved = ledger['reserved']
        if type(reserved) is not int or reserved < 0:
            raise ValueError('Invalid reserved amount')
        headroom = left - reserved
        output.update(provider_credits_left=left,
                      outstanding_reserved=reserved,
                      conservative_headroom=headroom,
                      minimum_one_fetch_headroom=1 + output['reserve_credits'],
                      snapshot_age_seconds=round(age, 1),
                      snapshot_fresh=age <= maximum_snapshot_age_seconds)
        if not output['snapshot_fresh']:
            output.update(status='STALE_SNAPSHOT', reason='Snapshot older than configured freshness; verified renewal and final guard required')
        elif headroom < 1 + output['reserve_credits']:
            output.update(status='BLOCKED_LOCAL_HEADROOM', reason='Insufficient conservative headroom after outstanding reservations')
        else:
            output.update(status='PREFLIGHT_POSSIBLE', reason='Local arithmetic passes; final provider quota, budget and request authorization still required')
    except (OSError, ValueError, TypeError, KeyError, OverflowError, json.JSONDecodeError):
        output['reason'] = 'Invalid or unavailable provider accounting evidence; no request authorized'
    return output
