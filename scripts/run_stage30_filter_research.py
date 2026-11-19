"""Research-only comparison of conservative signal filters.

Selection uses TRAINING only. HOLDOUT is evaluated once after a candidate is
selected. No live trades, API requests, or claims of broker price parity.
"""
from __future__ import annotations

import argparse
from functools import partial

from research.stage29_backtest import backtest, load_candles, existing_strategy_on_prefix


def conservative_signal(prefix, variant="baseline"):
    """Keep original directional signal unless a predeclared filter rejects it."""
    signal = existing_strategy_on_prefix(prefix)
    if signal == "NO TRADE" or variant == "baseline":
        return signal

    from indicators import calculate_indicators
    row = calculate_indicators(prefix).iloc[-1]
    try:
        close = float(row["Close"])
        atr = float(row["ATR_14"])
        rsi = float(row["RSI_14"])
        ema20 = float(row["EMA_20"])
        ema50 = float(row["EMA_50"])
    except (KeyError, TypeError, ValueError):
        return "NO TRADE"

    import math
    if not all(map(math.isfinite, (close, atr, rsi, ema20, ema50))) or atr <= 0:
        return "NO TRADE"

    # Predeclared, testable research hypotheses; NOT tuned on the holdout.
    if variant in ("trend", "trend_rsi"):
        if abs(ema20 - ema50) / atr < 0.35:
            return "NO TRADE"
        if (signal == "UP" and ema20 <= ema50) or (signal == "DOWN" and ema20 >= ema50):
            return "NO TRADE"
    if variant in ("rsi", "trend_rsi"):
        if signal == "UP" and not 50 <= rsi <= 65:
            return "NO TRADE"
        if signal == "DOWN" and not 35 <= rsi <= 50:
            return "NO TRADE"
    return signal


def choose_candidate(training_summaries, *, minimum_resolved=30):
    """Never choose from holdout performance or an inadequate training sample."""
    valid = [
        (name, stats)
        for name, stats in training_summaries.items()
        if stats["resolved"] >= minimum_resolved
        and stats["net_units"] > 0
        and stats["win_rate"] is not None
        and stats["win_rate"] > stats["breakeven_win_rate"]
    ]
    if not valid:
        return None
    return max(valid, key=lambda pair: (pair[1]["net_units"], pair[1]["resolved"]))[0]


def run_comparison(candles, payout=0.8, minimum_resolved=30):
    # The Stage 29 backtester enforces chronological boundaries, 15m settlements,
    # lookback continuity and the same independent holdout across every run.
    candidates = ("baseline", "trend", "rsi", "trend_rsi")
    summaries = {}
    for name in candidates:
        result = backtest(candles, signal_fn=partial(conservative_signal, variant=name), payout=payout)
        summaries[name] = result["training"]

    winner = choose_candidate(summaries, minimum_resolved=minimum_resolved)
    if winner is None:
        return {"training": summaries, "selected": None, "holdout": None,
                "decision": "NO TRADE: no training candidate passed minimum evidence and payout threshold"}

    # Only selected candidate gets holdout evaluation. It MUST NOT be re-selected
    # or modified based on its holdout result.
    final = backtest(candles, signal_fn=partial(conservative_signal, variant=winner), payout=payout)
    return {"training": summaries, "selected": winner, "holdout": final["holdout"],
            "decision": "RESEARCH ONLY: holdout must independently validate the selection"}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--csv", default="data/historical/eurusd_1min_1day.csv")
    p.add_argument("--payout", type=float, default=0.8)
    p.add_argument("--min-training-trades", type=int, default=30)
    args = p.parse_args()
    if args.min_training_trades < 30:
        p.error("At least 30 resolved training trades required")
    report = run_comparison(load_candles(args.csv), args.payout, args.min_training_trades)
    print("STAGE 30: TRAINING-ONLY FILTER COMPARISON (NO ORDERS)")
    for name, stats in report["training"].items():
        print(name, "resolved=", stats["resolved"],
              "win_rate=", "N/A" if stats["win_rate"] is None else f'{stats["win_rate"]:.2%}',
              "net_units=", stats["net_units"])
    print("selected:", report["selected"])
    if report["holdout"] is not None:
        s = report["holdout"]
        print("HOLDOUT:", "resolved=", s["resolved"],
              "win_rate=", "N/A" if s["win_rate"] is None else f'{s["win_rate"]:.2%}',
              "net_units=", s["net_units"])
        if s["resolved"] < 30:
            print("WARNING: Too few resolved holdout trades to validate accuracy")
    print(report["decision"])
    print("Caution: idealized candle-close fills; historical market data provenance not verified")


if __name__ == "__main__":
    main()
