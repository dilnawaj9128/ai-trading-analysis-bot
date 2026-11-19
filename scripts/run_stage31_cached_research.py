"""Stage 31: accelerated, parity-checked offline research.

No API calls or orders. Output may NOT be treated as broker performance.
Candidates are selected solely using training metrics, and the same fixed
holdout is inspected for the selected candidate, once.
"""
from __future__ import annotations

import argparse
import time

from research.stage29_backtest import backtest, load_candles
from research.stage31_cached_signals import CachedSignalResearch, VARIANTS, assert_prefix_parity
from scripts.run_stage30_filter_research import choose_candidate


def run(candles, payout=0.8, min_training_trades=30, check_parity=True):
    if min_training_trades < 30:
        raise ValueError("min_training_trades must be >= 30")
    cache = CachedSignalResearch(candles)
    if check_parity:
        assert_prefix_parity(candles, cache)

    results = {}
    for name in VARIANTS:
        # Existing backtest enforces the same gap/no-lookahead/expiry policy.
        results[name] = backtest(
            candles, signal_fn=cache.for_variant(name), payout=payout,
        )
    training = {name: results[name]["training"] for name in VARIANTS}
    selected = choose_candidate(training, minimum_resolved=min_training_trades)
    holdout = results[selected]["holdout"] if selected else None
    return {
        "training": training, "selected": selected, "holdout": holdout,
        "decision": ("NO TRADE: no training candidate passed safeguards" if selected is None
                     else "RESEARCH ONLY: inspect independently collected holdout data"),
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--csv", default="data/historical/eurusd_1min_1day.csv")
    p.add_argument("--payout", type=float, default=0.8)
    p.add_argument("--min-training-trades", type=int, default=30)
    args = p.parse_args()
    t0 = time.perf_counter()
    candles = load_candles(args.csv)
    print("STAGE 31: CACHED ANALYSIS-ONLY RESEARCH", flush=True)
    print(f"candles={len(candles)} parity_check=enabled", flush=True)
    report = run(candles, payout=args.payout,
                 min_training_trades=args.min_training_trades)
    for name, s in report["training"].items():
        rate = "N/A" if s["win_rate"] is None else f'{s["win_rate"]:.2%}'
        print(f"{name}: resolved={s['resolved']} win_rate={rate} net_units={s['net_units']}", flush=True)
    print("selected:", report["selected"], flush=True)
    if report["holdout"] is not None:
        s = report["holdout"]
        rate = "N/A" if s["win_rate"] is None else f'{s["win_rate"]:.2%}'
        print(f"HOLDOUT resolved={s['resolved']} win_rate={rate} net_units={s['net_units']}", flush=True)
        if s["resolved"] < 30:
            print("WARNING: Fewer than 30 resolved holdout signals", flush=True)
    print(report["decision"], flush=True)
    print(f"elapsed_seconds={time.perf_counter() - t0:.3f}", flush=True)
    print("Historical feed provenance unverified; no provider/broker execution parity.")


if __name__ == "__main__":
    main()
