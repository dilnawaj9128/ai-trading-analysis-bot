"""Stage 50G: next-open, offline, analysis-only walk-forward research."""

import pandas as pd

from research.stage29_backtest import summarize
from research.stage31_cached_signals import CachedSignalResearch, VARIANTS
from scripts.run_stage30_filter_research import choose_candidate

EXPIRY = 15
LOOKBACK = 60


def score_window(df, signal_fn, start, end, payout=0.80):
    """Completed candle i -> entry Open[i+1] -> exit Close[i+15]."""
    if not 0 < payout <= 1:
        raise ValueError("Invalid payout")
    if not 0 <= start < end <= len(df):
        raise ValueError("Invalid window")

    trades = []
    checked = no_trade = skipped = 0

    continuity = df["timestamp"].diff().eq(
        pd.Timedelta(minutes=1)
    )

    i = max(start, LOOKBACK - 1)

    while i + EXPIRY < end:
        left = i - LOOKBACK + 1

        if not continuity.iloc[left + 1:i + EXPIRY + 1].all():
            skipped += 1
            i += 1
            continue

        prefix = df.iloc[:i + 1].copy()
        signal = signal_fn(prefix)

        if signal not in ("UP", "DOWN", "NO TRADE"):
            raise ValueError("Invalid strategy signal")

        checked += 1

        if signal == "NO TRADE":
            no_trade += 1
            i += 1
            continue

        entry_index = i + 1
        expiry_index = i + EXPIRY

        entry_time = df.timestamp.iloc[entry_index]
        expiry_time = (
            df.timestamp.iloc[expiry_index]
            + pd.Timedelta(minutes=1)
        )

        if expiry_time - entry_time != pd.Timedelta(minutes=15):
            raise ValueError("Expiry timing mismatch")

        entry = float(df.Open.iloc[entry_index])
        exit_price = float(df.Close.iloc[expiry_index])

        if entry == exit_price:
            result = "PUSH"
        elif (
            (signal == "UP" and exit_price > entry)
            or (signal == "DOWN" and exit_price < entry)
        ):
            result = "WIN"
        else:
            result = "LOSS"

        trades.append({
            "signal_index": i,
            "entry_index": entry_index,
            "expiry_index": expiry_index,
            "signal": signal,
            "entry": entry,
            "exit": exit_price,
            "result": result,
        })

        i += EXPIRY

    return {
        "stats": summarize(
            trades,
            no_trade=no_trade,
            skipped=skipped,
            checked=checked,
            payout=payout,
        ),
        "trades": trades,
    }


def walk_forward_next_open(
    df,
    initial_train=720,
    test_size=180,
    payout=0.80,
    min_training_trades=30,
):
    if initial_train < LOOKBACK + EXPIRY:
        raise ValueError("Insufficient training window")
    if test_size <= EXPIRY or min_training_trades < 30:
        raise ValueError("Invalid evaluation settings")
    if not 0 < payout <= 1:
        raise ValueError("Invalid payout")

    data = df.copy().reset_index(drop=True)

    if (
        data.timestamp.isna().any()
        or data.timestamp.dt.tz is None
        or data.timestamp.duplicated().any()
        or not data.timestamp.is_monotonic_increasing
    ):
        raise ValueError("Invalid timestamps")

    cache = CachedSignalResearch(data)
    folds = []
    all_trades = []

    for start in range(
        initial_train, len(data) - EXPIRY, test_size
    ):
        end = min(start + test_size, len(data))
        training = {}

        for variant in VARIANTS:
            training[variant] = score_window(
                data,
                cache.for_variant(variant),
                LOOKBACK - 1,
                start,
                payout,
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
                start,
                end,
                payout,
            )

            for trade in test["trades"]:
                assert start <= trade["signal_index"]
                assert trade["expiry_index"] < end

            all_trades.extend(test["trades"])

        folds.append({
            "test_start": start,
            "test_end": end,
            "selected": selected,
            "training": training,
            "test": test,
        })

    return {
        "folds": folds,
        "test_trades": all_trades,
        "aggregate": summarize(
            all_trades, 0, 0, 0, payout
        ),
        "entry_model": "NEXT_CANDLE_OPEN",
        "expiry_minutes": 15,
        "dataset_origin_verified": False,
        "forward_accuracy_proven": False,
        "analysis_only": True,
        "execution_enabled": False,
    }
