"""Offline deployment/readiness check; never fetches provider data or prints keys."""
from __future__ import annotations
import json
from dashboard.real_data_ops import operational_status, recent_events


def main():
    status = operational_status()
    status["recent_monitor_events"] = recent_events(limit=5)
    print(json.dumps(status, sort_keys=True, indent=2))
    print("NO HTTP. NO TRADING SIGNALS. NO BROKER ORDERS.")
    # Empty/stale history is a data-freshness warning, not a failed installation.
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
