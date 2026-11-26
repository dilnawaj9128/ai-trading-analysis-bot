"""Read-only regular EUR/USD provider feed class verification.

NO HTTP, API key, broker calls, strategy overrides, or credit journal writes.
Use --csv with an existing saved research capture to check candle quality and
a known SHA256. It does not verify account-specific delivery mode.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from market_data.regular_forex_feed_evidence import (
    classify_saved_csv, FeedEvidenceError,
)

def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--csv", type=Path, required=True)
    p.add_argument("--sha256", default=None,
                   help="Optional immutable SHA256 from previous successful capture")
    args = p.parse_args(argv)
    try:
        report = classify_saved_csv(args.csv, expected_sha256=args.sha256)
    except (OSError, ValueError, TypeError, FeedEvidenceError) as exc:
        print(json.dumps({
            "status": "BLOCKED_OR_INVALID_CAPTURE",
            "error_type": type(exc).__name__,
            "live_signal": "NO TRADE",
            "no_extra_http_requests": True,
            "broker_orders": 0,
        }, indent=2))
        return 2
    print(json.dumps(report, indent=2))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
