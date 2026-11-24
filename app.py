"""Safe analysis-only CLI entry point.

The old Stage 6 app imports a retired direct Twelve Data provider.
That transport is intentionally disabled by Stage 52. This entry point
analyzes already-saved, completed EUR/USD candles without HTTP requests,
API credits, broker connections, or orders.

Historical UNCERTAIN requests and all credit/authorization journals remain
unchanged. A stale/unverified feed must not be upgraded to a directional
signal.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from scripts.analyze_saved_real_candles import analyze

DEFAULT_CSV = Path("data/real_market/latest_eurusd_completed.csv")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", type=Path, default=DEFAULT_CSV,
                        help="Path to saved completed EUR/USD 1-minute candles")
    args = parser.parse_args(argv)

    try:
        report = analyze(args.csv, now=datetime.now(timezone.utc))
    except (FileNotFoundError, OSError, ValueError, KeyError, RuntimeError) as exc:
        report = {
            "source": "saved_twelve_data_csv",
            "signal": "NO TRADE",
            "reasons": [
                "Offline analysis blocked: validated completed candle data unavailable."
            ],
            "error_type": type(exc).__name__,
            "analysis_only": True,
            "execution_enabled": False,
        }
        print(json.dumps(report, indent=2))
        print("No HTTP requests, broker orders or authorization-state changes.")
        return 1

    print(json.dumps(report, indent=2))
    print("Offline analysis only. No HTTP requests, API credits or broker orders.")
    if report.get("stale") or report.get("feed_mode") != "verified":
        print("Feed stale/unverified: directional signals are not authorized.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
