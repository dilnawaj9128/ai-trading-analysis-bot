"""Stage 54: offline REAL-data research audit before Streamlit UI.

No network calls; no orders. Requires actual locally saved provider candles.
Historical backtest strategies are research only and are NOT the same as
production direction signals (which stay NO TRADE without broker/feed parity).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from datetime import datetime, timezone
from pathlib import Path


def evaluate(csv_path, *, minimum_resolved=100, payout=0.8, run_walk_forward=True):
    if not isinstance(minimum_resolved, int) or minimum_resolved < 30:
        raise ValueError("minimum_resolved must be >=30")
    if not isinstance(payout, (float, int)) or not (0 < payout <= 1):
        raise ValueError("payout must lie in (0,1]")
    from scripts.run_stage45_dataset_audit import parse_candles, quality
    from research.stage29_backtest import load_candles, backtest

    path = Path(csv_path)
    rows = parse_candles(path)
    q = quality(rows)
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    report = {
        "status": "BLOCKED", "source": str(path), "source_sha256": digest,
        "market": "EUR/USD", "timeframe": "1min", "expiry_minutes": 15,
        "analysis_only": True, "execution_enabled": False, "api_requests": 0,
        "quality": q, "historical_strategy": "stage29_existing_research_strategy",
        "live_signal": "NO TRADE", "broker_feed_parity_verified": False,
        "minimum_resolved_required": minimum_resolved,
        "warnings": ["Offline research is not verified Quotex price parity or future accuracy."],
    }
    if not q["continuous_one_minute_candles"]:
        report["reason"] = "DATA_QUALITY_BLOCKED: duplicate, gap, irregular, or backward candles"
        return report
    if len(rows) < 90:
        report["status"] = "INSUFFICIENT_DATA"
        report["reason"] = "Fewer than 90 continuous 1m candles"
        return report

    candles = load_candles(path)
    result = backtest(candles, payout=float(payout))
    holdout = result["holdout"]
    report["stage29"] = {
        "method": result["method"], "training": result["training"],
        "holdout": holdout,
    }
    report["stage29"]["trades_sha256"] = hashlib.sha256(
        json.dumps(result["trades"], sort_keys=True, default=str).encode()
    ).hexdigest()
    resolved = int(holdout["resolved"])
    report["status"] = "INSUFFICIENT_DATA"
    report["reason"] = "Fewer than minimum independently resolved HOLDOUT signals"
    report["historical_holdout_resolved"] = resolved

    # A chronological walk-forward must not be conflated with the holdout test.
    # Existing Stage 36 refuses weak training windows or short datasets.
    if run_walk_forward:
        if len(candles) < 900:
            report["walk_forward"] = {"status": "INSUFFICIENT_DATA", "reason": "At least 900 contiguous candles needed for default expanding-window research"}
        else:
            from scripts.run_stage36_walk_forward import walk_forward
            wf = walk_forward(candles, initial_train=720, test_size=180,
                              payout=float(payout), min_training_trades=30)
            agg = wf["aggregate"]
            report["walk_forward"] = {"status": "EVALUATED", "folds": len(wf["folds"]),
                                      "selected_folds": sum(f["selected"] is not None for f in wf["folds"]),
                                      "aggregate": agg}
            if int(agg["resolved"]) < minimum_resolved:
                report["walk_forward"]["status"] = "INSUFFICIENT_DATA"
    if resolved >= minimum_resolved:
        report["status"] = "EXPLORATORY_ONLY"
        report["reason"] = "Enough historical outcomes to inspect; independence, parity and forward predictive skill not established"
        if holdout["net_units"] <= 0:
            report["reason"] = "No positive historical net units at given payout"
        elif report.get("walk_forward", {}).get("status") != "EVALUATED":
            report["reason"] = "Walk-forward evidence still insufficient; never treat as proven signal"
    return report


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--csv", default="data/real_market/stage52d_new_completed.csv")
    p.add_argument("--out", default="data/research/real_data_validation.json")
    p.add_argument("--minimum-resolved", type=int, default=100)
    p.add_argument("--payout", type=float, default=0.8)
    p.add_argument("--no-walk-forward", action="store_true")
    args = p.parse_args(argv)
    try:
        result = evaluate(args.csv, minimum_resolved=args.minimum_resolved,
                          payout=args.payout, run_walk_forward=not args.no_walk_forward)
    except (ImportError, OSError, ValueError, KeyError, TypeError, AssertionError) as e:
        print("REAL_DATA_VALIDATION: BLOCKED", type(e).__name__, str(e))
        return 2
    target = Path(args.out)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(result, indent=2, sort_keys=True, default=str) + "\n", encoding="utf8")
    print("REAL_DATA_VALIDATION:", result["status"])
    print("SOURCE_SHA256:", result["source_sha256"])
    print("CANDLES:", result["quality"]["rows"])
    print("QUALITY_PASS:", result["quality"]["continuous_one_minute_candles"])
    print("HOLDOUT_RESOLVED:", result.get("historical_holdout_resolved", 0))
    print("REASON:", result.get("reason", ""))
    print("LIVE_SIGNAL: NO TRADE (broker parity unverified)")
    print("NO HTTP / NO BROKER ORDERS")
    print("REPORT:", target)
    return 0 if result["status"] == "EXPLORATORY_ONLY" else 1


if __name__ == "__main__":
    raise SystemExit(main())
