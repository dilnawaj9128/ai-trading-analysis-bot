"""One-command historical scorecard, plus safe prospective observe/settle.

Default: audit saved 120- and 1440-candle EUR/USD datasets, if present.
Optional --observe CSV: snapshot a fresh hypothetical decision BEFORE outcome.
Optional --settle CSV: reconcile previously observed 15-minute outcomes.
Never sends API requests, connects to brokers or claims verified accuracy.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from research.real_prediction_campaign import (
    historical_campaign, observe, settle_pending, prospective_scorecard,
)

DEFAULT_CSVS = (
    "data/real_market/stage52d_new_completed.csv",
    "data/historical/eurusd_1min_1day.csv",
)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", action="append", dest="datasets", help="Historic saved EUR/USD 1m candle CSV; repeatable")
    parser.add_argument("--observe", metavar="FRESH_COMPLETED_CSV", help="Record current research hypothesis once; data must be fresh")
    parser.add_argument("--settle", metavar="LATER_COMPLETED_CSV", help="Settle earlier observations after 15m")
    parser.add_argument("--journal", default="data/research/prospective_accuracy")
    parser.add_argument("--out-dir", default="data/research/real_accuracy_campaign")
    parser.add_argument("--payout", type=float, default=0.80)
    args = parser.parse_args(argv)
    if not 0 < args.payout <= 1:
        parser.error("--payout must be in (0,1]")
    if args.observe and args.settle:
        parser.error("Use --observe and --settle in separate runs")
    paths = args.datasets if args.datasets is not None else [p for p in DEFAULT_CSVS if Path(p).is_file()]
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    report = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "symbol": "EUR/USD", "timeframe": "1min", "expiry_minutes": 15,
        "payout_assumption": args.payout,
        "historical": historical_campaign(paths, payout=args.payout) if paths else {"status": "NO_SAVED_DATASETS"},
        "prospective": None,
        "live_signal": "NO TRADE", "research_only": True,
        "http_requests": 0, "broker_orders": 0,
    }
    if args.observe:
        p, obs = observe(args.observe, journal=args.journal)
        print("OBSERVATION_SAVED:", p)
        print("RESEARCH_HYPOTHESIS:", obs["research_hypothesis"])
        print("EXPIRY_UTC:", obs["expiry_time_utc"])
        print("LIVE SIGNAL: NO TRADE — broker/feed parity unverified")
    if args.settle:
        settlement = settle_pending(journal=args.journal, later_csv=args.settle)
        report["settlement_attempt"] = settlement
        print("NEW_SETTLEMENTS:", len(settlement["settled"]))
        print("PENDING_OR_BLOCKED:", len(settlement["still_pending_or_blocked"]))
    report["prospective"] = prospective_scorecard(args.journal, payout=args.payout)
    dest = out / "latest_research_scorecard.json"
    dest.write_text(json.dumps(report, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    print("HISTORICAL_DATASETS:", len(report["historical"].get("datasets", [])))
    print("HISTORICAL_NONPUSH:", report["historical"].get("overall_descriptive_only", {}).get("nonpush", 0))
    print("HISTORICAL_ONLY: Exploratory, NOT proof of predictive skill")
    print("PROSPECTIVE_RESULTS:", report["prospective"]["counts"])
    print("PROSPECTIVE_STATUS:", report["prospective"]["statistical_audit"]["status"])
    print("REPORT:", dest)
    print("NO HTTP / NO BROKER ORDERS / LIVE SIGNAL: NO TRADE")
    return 2 if report["historical"].get("rejected_datasets") or report["prospective"]["invalid_evidence"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
