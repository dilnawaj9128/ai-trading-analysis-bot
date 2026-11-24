"""Conservative, no-network dashboard credit-repair controls.

Never settles an unknown request, changes provider snapshot or gives API approval.
"""
from __future__ import annotations


def credit_repair_preview():
    try:
        from dashboard.twelve_data_readiness import readiness
        details = readiness()
        left = details.get('provider_credits_left')
        reserved = details.get('outstanding_reserved')
        needed = details.get('minimum_one_fetch_headroom')
        headroom = details.get('conservative_headroom')
        # If evidence is absent, do not duplicate the authoritative guard;
        # it remains responsible for refusing unsafe operations.
        blocked = (type(headroom) is int and type(needed) is int
                   and headroom < needed)
        if blocked:
            message = (f'Last recorded provider credits {left}, pending reservations {reserved}, '
                       f'headroom {headroom}, required headroom {needed}. '
                       'Only verified receipts or genuine refreshed quota can change this.')
        else:
            message = details.get('reason', 'Final provider authorization required')
        return {'fetch_headroom_blocked': blocked, 'message': message,
                'provider_status': details.get('status', 'UNKNOWN'),
                'provider_requests': 0}
    except (OSError, ValueError, KeyError, TypeError, ImportError):
        return {'fetch_headroom_blocked': False,
                'message': 'Local preflight unavailable; final request authorization remains mandatory',
                'provider_status': 'UNKNOWN', 'provider_requests': 0}


def reconcile_receipts_safely():
    """Existing reconciler is sole authority for any ledger mutations."""
    try:
        from market_data.verified_reservation_settlement import (
            reconcile_verified_historical, VerifiedSettlementBlocked,
        )
        result = reconcile_verified_historical()
        if result.get('status') != 'RECONCILED':
            return {'ok': False, 'reason': 'UNEXPECTED_RECONCILIATION_RESULT'}
        return {'ok': True, 'outstanding_reserved': result['outstanding_reserved'],
                'settled_count': len(result.get('settled_request_prefixes', [])),
                'provider_requests': 0}
    except (OSError, ValueError, TypeError, KeyError, VerifiedSettlementBlocked) as exc:
        return {'ok': False, 'reason': type(exc).__name__, 'provider_requests': 0}
