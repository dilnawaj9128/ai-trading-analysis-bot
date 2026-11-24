"""One-time offline reconciliation of demonstrably verified Twelve Data calls.

No HTTP, API keys, background actions or broker orders. It will NEVER settle
legacy or UNCERTAIN reservations, or successful requests without a journal.
"""
import json
from market_data.verified_reservation_settlement import (
    reconcile_verified_historical, VerifiedSettlementBlocked,
)


def main():
    try:
        result = reconcile_verified_historical()
    except (OSError, ValueError, TypeError, VerifiedSettlementBlocked) as exc:
        print('RECONCILIATION_BLOCKED:', type(exc).__name__)
        print('Existing ledger unchanged unless a prior verified ID was already safely settled.')
        print('DO NOT DELETE OR RESET ACCOUNTING FILES.')
        raise SystemExit(1)
    print('VERIFIED_RESERVATION_RECONCILIATION:')
    print(json.dumps(result, indent=2, sort_keys=True))
    print('NO API REQUESTS. NO BROKER ORDERS.')

if __name__ == '__main__':
    main()
