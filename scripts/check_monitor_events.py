"""Offline read-only historical monitoring audit; no API calls."""
import json
from dashboard.real_data_ops import monitor_event_audit

def main():
    result = monitor_event_audit()
    print('=== MONITORING EVENT AUDIT — READ ONLY ===')
    print(json.dumps(result, indent=2, sort_keys=True))
    if result['unmatched_fetch_starts']:
        print('ATTENTION: unmatched FETCH_STARTED is UNKNOWN, not verified success or failure.')
    print('NO API REQUESTS / NO LEDGER CHANGES / NO BROKER ORDERS')

if __name__ == '__main__':
    main()
