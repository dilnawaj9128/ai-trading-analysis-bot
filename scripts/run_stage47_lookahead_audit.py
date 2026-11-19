"""Stage 47: offline signal-timing and look-ahead diagnostics.

Tests future perturbation invariance and training-selection isolation.
A PASS is evidence for tested checkpoints, not proof of all possible
strategies, dates, or hidden data dependencies.
"""

import argparse
import json
from pathlib import Path

import pandas as pd

from research.stage29_backtest import load_candles
from research.stage31_cached_signals import (
    CachedSignalResearch,
    VARIANTS,
)
from scripts.run_stage30_filter_research import choose_candidate
from scripts.run_stage36_walk_forward import (
    LOOKBACK,
    EXPIRY,
    score_window,
    walk_forward,
)
from scripts.run_stage41_evidence_audit import (
    sha256_file,
    write_evidence_report,
)
from scripts.run_stage45_dataset_audit import (
    parse_candles,
    quality,
)

DEFAULT_CSV = Path("data/historical/eurusd_1min_1day.csv")
DEFAULT_OUT = Path("data/research/stage47")

VALID_SIGNALS = {"UP", "DOWN", "NO TRADE"}


def validate_frame(df):
    if not isinstance(df, pd.DataFrame):
        raise ValueError("Dataframe required")

    required = {"timestamp", "Open", "High", "Low", "Close"}
    if not required.issubset(df.columns):
        raise ValueError("Missing candle columns")

    if len(df) < LOOKBACK + EXPIRY + 2:
        raise ValueError("Insufficient candles")

    stamps = df["timestamp"]

    if (
        stamps.isna().any()
        or not isinstance(stamps.dtype, pd.DatetimeTZDtype)
        or stamps.duplicated().any()
        or not stamps.is_monotonic_increasing
    ):
        raise ValueError("Invalid timestamps")

    if not stamps.diff().iloc[1:].eq(
        pd.Timedelta(minutes=1)
    ).all():
        raise ValueError("Noncontiguous candles")

    for column in ("Open", "High", "Low", "Close"):
        values = pd.to_numeric(df[column], errors="raise")
        if not (
            values.notna().all()
            and (values > 0).all()
            and values.map(
                lambda v: bool(pd.notna(v)) and abs(float(v)) < float("inf")
            ).all()
        ):
            raise ValueError("Invalid OHLC values")

    if (
        (df["High"] < df[["Open", "Low", "Close"]].max(axis=1)).any()
        or (df["Low"] > df[["Open", "High", "Close"]].min(axis=1)).any()
    ):
        raise ValueError("Inconsistent OHLC")


def alter_future(df, cutoff, change=0.01):
    """Only change rows STRICTLY AFTER cutoff, never the past."""
    if type(cutoff) is not int or not 0 <= cutoff < len(df) - 1:
        raise ValueError("Invalid cutoff")
    if not 0 < change < 0.5:
        raise ValueError("Invalid perturbation")

    modified = df.copy(deep=True)

    # All OHLC fields shift together, preserving candle integrity.
    for col in ("Open", "High", "Low", "Close"):
        modified.loc[
            modified.index[cutoff + 1:], col
        ] = (
            modified.loc[
                modified.index[cutoff + 1:], col
            ].astype(float) * (1 + change)
        )

    if not df.iloc[:cutoff + 1].equals(
        modified.iloc[:cutoff + 1]
    ):
        raise ValueError("Past candles were changed")

    return modified


def check_signal_invariance(
    df, cutoff, *,
    variants=VARIANTS,
    cache_factory=CachedSignalResearch,
):
    """Compare full, future-modified and prefix-only indicator caches."""
    validate_frame(df)

    if cutoff < LOOKBACK:
        raise ValueError("Checkpoint lacks sufficient warmup")

    changed = alter_future(df, cutoff)
    prefix = df.iloc[:cutoff + 1].copy()

    original_cache = cache_factory(df)
    altered_cache = cache_factory(changed)
    prefix_cache = cache_factory(prefix)

    results = []

    for variant in variants:
        original = original_cache.for_variant(variant)(prefix.copy())
        altered = altered_cache.for_variant(variant)(prefix.copy())
        isolated = prefix_cache.for_variant(variant)(prefix.copy())

        if any(
            signal not in VALID_SIGNALS
            for signal in (original, altered, isolated)
        ):
            raise ValueError("Unexpected signal result")

        same = original == altered == isolated

        results.append({
            "variant": str(variant),
            "checkpoint_index": cutoff,
            "signal": original,
            "future_modified_signal": altered,
            "prefix_only_signal": isolated,
            "passed": same,
        })

    return results


def check_training_isolation(
    df, test_start, *,
    payout=0.8,
    minimum_resolved=30,
    variants=VARIANTS,
    cache_factory=CachedSignalResearch,
    scorer=score_window,
    selector=choose_candidate,
):
    """Selection must be unchanged if only future test prices change."""
    validate_frame(df)

    if not LOOKBACK < test_start < len(df) - 1:
        raise ValueError("Invalid test start")

    changed = alter_future(df, test_start - 1)
    original_cache = cache_factory(df)
    modified_cache = cache_factory(changed)

    original_scores = {}
    modified_scores = {}
    mismatches = []

    for variant in variants:
        original_scores[variant] = scorer(
            df,
            original_cache.for_variant(variant),
            start=LOOKBACK - 1,
            end=test_start,
            payout=payout,
        )["stats"]

        modified_scores[variant] = scorer(
            changed,
            modified_cache.for_variant(variant),
            start=LOOKBACK - 1,
            end=test_start,
            payout=payout,
        )["stats"]

        if original_scores[variant] != modified_scores[variant]:
            mismatches.append(str(variant))

    original_selected = selector(
        original_scores, minimum_resolved=minimum_resolved
    )
    modified_selected = selector(
        modified_scores, minimum_resolved=minimum_resolved
    )

    return {
        "test_start": test_start,
        "original_selected": original_selected,
        "future_modified_selected": modified_selected,
        "training_score_mismatches": mismatches,
        "passed": (
            not mismatches
            and original_selected == modified_selected
        ),
    }


def audit(df, *,
          initial_train=720,
          test_size=180,
          payout=0.8,
          min_training_trades=30,
          cache_factory=CachedSignalResearch):
    validate_frame(df)

    research = walk_forward(
        df,
        initial_train=initial_train,
        test_size=test_size,
        payout=payout,
        min_training_trades=min_training_trades,
    )

    checkpoints = set()

    for fold in research["folds"]:
        start = fold["test_start"]
        end = fold["test_end"]

        if start >= LOOKBACK and start < len(df) - 1:
            checkpoints.add(start)
        if end - 1 >= LOOKBACK and end - 1 < len(df) - 1:
            checkpoints.add(end - 1)

        if fold["test"] is not None:
            for trade in fold["test"]["trades"]:
                index = trade["signal_index"]
                if LOOKBACK <= index < len(df) - 1:
                    checkpoints.add(index)

    signal_checks = []
    for index in sorted(checkpoints):
        signal_checks.extend(
            check_signal_invariance(
                df, index, cache_factory=cache_factory
            )
        )

    selection_checks = []
    for fold in research["folds"]:
        selection_checks.append(
            check_training_isolation(
                df,
                fold["test_start"],
                payout=payout,
                minimum_resolved=min_training_trades,
                cache_factory=cache_factory,
            )
        )

    signal_failures = sum(
        not item["passed"] for item in signal_checks
    )
    selection_failures = sum(
        not item["passed"] for item in selection_checks
    )

    passed = signal_failures == 0 and selection_failures == 0

    return {
        "stage": 47,
        "status": (
            "CHECKPOINTS_PASSED"
            if passed else "BLOCKED_LOOKAHEAD_MISMATCH"
        ),
        "signal_checks": len(signal_checks),
        "signal_failures": signal_failures,
        "selection_checks": len(selection_checks),
        "selection_failures": selection_failures,
        "signal_results": signal_checks,
        "selection_results": selection_checks,
        "tested_future_perturbation": 0.01,
        "limitations": [
            "Only selected checkpoints and one perturbation tested",
            "Does not audit third-party provider provenance",
            "Does not establish live accuracy or profitability",
            "Does not prove absence of every possible leakage path",
        ],
        "dataset_origin_verified": False,
        "forward_accuracy_proven": False,
        "directional_signals_authorized": False,
        "analysis_only": True,
        "execution_enabled": False,
        "api_requests_executed": 0,
    }


def run(csv_path=DEFAULT_CSV):
    raw = parse_candles(csv_path)

    if not quality(raw)["continuous_one_minute_candles"]:
        raise ValueError("Historical data quality failed")

    data = load_candles(str(csv_path))

    if len(raw) != len(data):
        raise ValueError("Historical loader changed candle count")

    validate_frame(data)

    result = audit(data)

    return {
        "dataset_sha256": sha256_file(csv_path),
        **result,
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument(
        "action", nargs="?", choices=("audit", "export"),
        default="audit",
    )
    p.add_argument("--csv", type=Path, default=DEFAULT_CSV)
    p.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = p.parse_args()

    try:
        result = run(args.csv)

        print("=== STAGE 47 LOOK-AHEAD AUDIT ===")
        print(json.dumps(result, indent=2))

        if args.action == "export":
            path, created = write_evidence_report(
                result, args.out
            )
            print("report_path:", path)
            print("new_report_created:", created)

    except (OSError, ValueError, TypeError, KeyError) as exc:
        p.exit(1, f"BLOCKED: {type(exc).__name__}: {exc}\n")

    print("API requests: 0")
    print("Trading execution: DISABLED")


if __name__ == "__main__":
    main()
