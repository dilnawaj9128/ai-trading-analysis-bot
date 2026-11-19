"""Stage 36: Offline expanding-window walk-forward validation.

No API requests, broker orders, or automatic trading.
Existing historical data may already have been inspected,
so these results are exploratory, not independent proof.
"""

import argparse
from functools import partial

import pandas as pd

from research.stage29_backtest import load_candles, summarize
from research.stage31_cached_signals import CachedSignalResearch, VARIANTS
from scripts.run_stage30_filter_research import choose_candidate

EXPIRY = 15
LOOKBACK = 60


def score_window(df, signal_fn, start, end, payout=0.80):
    """Score signals only when entry AND expiry lie inside this window.

    start inclusive, end exclusive.
    Signal function receives only candles through index i.
    """
    trades = []
    checked = no_trade = skipped = 0

    contiguous = df["timestamp"].diff().eq(
        pd.Timedelta(minutes=1)
    )

    i = max(start, LOOKBACK - 1)

    while i + EXPIRY < end:
        # Both the lookback and settlement must be contiguous.
        left = max(0, i - LOOKBACK + 1)

        if not contiguous.iloc[left + 1:i + EXPIRY + 1].all():
            skipped += 1
            i += 1
            continue

        prefix = df.iloc[:i + 1].copy()
        signal = signal_fn(prefix)

        if signal not in ("UP", "DOWN", "NO TRADE"):
            raise ValueError("Unexpected strategy signal")

        checked += 1

        if signal == "NO TRADE":
            no_trade += 1
            i += 1
            continue

        entry = float(df["Close"].iloc[i])
        exit_price = float(df["Close"].iloc[i + EXPIRY])

        if exit_price == entry:
            result = "PUSH"
        elif (exit_price > entry) == (signal == "UP"):
            result = "WIN"
        else:
            result = "LOSS"

        trades.append({
            "signal_index": i,
            "expiry_index": i + EXPIRY,
            "signal_time": df["timestamp"].iloc[i].isoformat(),
            "signal": signal,
            "entry": entry,
            "exit": exit_price,
            "result": result,
        })

        # No overlapping directional positions.
        i += EXPIRY

    stats = summarize(
        trades,
        no_trade=no_trade,
        skipped=skipped,
        checked=checked,
        payout=payout,
    )

    return {"stats": stats, "trades": trades}


def walk_forward(
    df,
    initial_train=720,
    test_size=180,
    payout=0.80,
    min_training_trades=30,
    cache_factory=CachedSignalResearch,
):
    """Expanding training, fixed sequential test windows.

    Training outcomes must settle BEFORE the test window starts.
    Only training performance selects a candidate.
    """
    if initial_train < 60 + EXPIRY:
        raise ValueError("Training window too small")

    if test_size <= EXPIRY:
        raise ValueError("Test window too small")

    if min_training_trades < 30:
        raise ValueError("At least 30 training trades required")

    if len(df) < initial_train + EXPIRY + 1:
        raise ValueError("Not enough candles")

    if not 0 < payout <= 1:
        raise ValueError("Invalid payout")

    data = df.copy().reset_index(drop=True)

    if (
        not isinstance(data["timestamp"].dtype, pd.DatetimeTZDtype)
        or data["timestamp"].isna().any()
        or data["timestamp"].duplicated().any()
        or not data["timestamp"].is_monotonic_increasing
    ):
        raise ValueError("Sorted, unique, timezone-aware timestamps required")

    cache = cache_factory(data)

    folds = []
    all_test_trades = []

    for test_start in range(initial_train, len(data) - EXPIRY, test_size):
        test_end = min(test_start + test_size, len(data))

        training = {}

        # Important: selection uses TRAINING outcomes only.
        for variant in VARIANTS:
            training[variant] = score_window(
                data,
                cache.for_variant(variant),
                start=LOOKBACK - 1,
                end=test_start,
                payout=payout,
            )["stats"]

        selected = choose_candidate(
            training,
            minimum_resolved=min_training_trades,
        )

        test = None

        if selected is not None:
            test = score_window(
                data,
                cache.for_variant(selected),
                start=test_start,
                end=test_end,
                payout=payout,
            )

            # Defensive check against boundary leakage.
            for trade in test["trades"]:
                assert test_start <= trade["signal_index"]
                assert trade["expiry_index"] < test_end

            all_test_trades.extend(test["trades"])

        folds.append({
            "train_end": test_start,
            "test_start": test_start,
            "test_end": test_end,
            "selected": selected,
            "training": training,
            "test": test,
        })

    aggregate = summarize(
        all_test_trades,
        no_trade=0,
        skipped=0,
        checked=0,
        payout=payout,
    )

    return {
        "folds": folds,
        "aggregate": aggregate,
        "test_trades": all_test_trades,
        "analysis_only": True,
        "execution_enabled": False,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--csv",
        default="data/historical/eurusd_1min_1day.csv",
    )
    parser.add_argument("--train", type=int, default=720)
    parser.add_argument("--test", type=int, default=180)
    parser.add_argument("--payout", type=float, default=0.80)
    parser.add_argument("--min-training-trades", type=int, default=30)

    args = parser.parse_args()

    candles = load_candles(args.csv)

    report = walk_forward(
        candles,
        initial_train=args.train,
        test_size=args.test,
        payout=args.payout,
        min_training_trades=args.min_training_trades,
    )

    print("\n=== STAGE 36 WALK-FORWARD VALIDATION ===")
    print("Candles:", len(candles))
    print("Expiry: 15 minutes")
    print("API calls: 0")
    print("Execution: DISABLED")

    for number, fold in enumerate(report["folds"], 1):
        print(f"\n--- FOLD {number} ---")
        print("Training ends at index:", fold["train_end"])
        print(
            "Test indexes:",
            fold["test_start"], "to", fold["test_end"] - 1,
        )
        print("Selected strategy:", fold["selected"])

        if fold["test"] is None:
            print("NO TRADE: training evidence insufficient")
            continue

        stats = fold["test"]["stats"]

        print("Resolved:", stats["resolved"])
        print("Wins:", stats["wins"])
        print("Losses:", stats["losses"])
        print("Pushes:", stats["pushes"])
        print(
            "Win rate:",
            "N/A" if stats["win_rate"] is None
            else f'{stats["win_rate"]:.2%}',
        )
        print("Net units:", stats["net_units"])

    aggregate = report["aggregate"]

    print("\n=== AGGREGATE WALK-FORWARD RESULTS ===")
    print("Resolved:", aggregate["resolved"])
    print("Wins:", aggregate["wins"])
    print("Losses:", aggregate["losses"])
    print("Pushes:", aggregate["pushes"])
    print(
        "Win rate:",
        "N/A" if aggregate["win_rate"] is None
        else f'{aggregate["win_rate"]:.2%}',
    )
    print("Net units:", aggregate["net_units"])
    print(
        "Break-even win rate:",
        f'{aggregate["breakeven_win_rate"]:.2%}',
    )

    if aggregate["resolved"] < 100:
        print("VERDICT: INSUFFICIENT EVIDENCE")
    elif aggregate["net_units"] <= 0:
        print("VERDICT: NO POSITIVE HISTORICAL EDGE")
    else:
        print("VERDICT: RESEARCH ONLY - INDEPENDENT VALIDATION REQUIRED")

    print("\nWARNING: Existing historical data may have been inspected.")
    print("Provider provenance and broker price parity are unverified.")
    print("No live prediction accuracy or profit guarantee.")


if __name__ == "__main__":
    main()
