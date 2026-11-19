"""Independent settlement audit for Stage 36 walk-forward trades.

Offline only. Uses historical candle prices and existing Stage 36
research results. Does not create trading orders or call APIs.
"""

import argparse
import json
import math
from datetime import timedelta
from pathlib import Path

from research.stage29_backtest import load_candles
from scripts.run_stage36_walk_forward import walk_forward
from scripts.run_stage41_evidence_audit import (
    sha256_file,
    write_evidence_report,
)
from scripts.run_stage45_dataset_audit import (
    parse_candles,
    quality,
)

DEFAULT_CSV = Path("data/historical/eurusd_1min_1day.csv")
DEFAULT_OUT = Path("data/research/stage46/walk_forward_reports")

EXPIRY = 15
PRICE_TOLERANCE = 1e-10


def audit_walk_forward(candles, report, payout=0.8):
    """Recalculate outcome from underlying candles, not trade result."""
    if not (0 < payout <= 1):
        raise ValueError("Invalid payout")

    data = candles.copy()
    if len(data) < 100 or "timestamp" not in data or "Close" not in data:
        raise ValueError("Invalid candle data")

    if (
        data["timestamp"].isna().any()
        or data["timestamp"].dt.tz is None
        or data["timestamp"].duplicated().any()
        or not data["timestamp"].is_monotonic_increasing
    ):
        raise ValueError("Invalid candle timestamps")

    if not data["timestamp"].diff().iloc[1:].eq(
        timedelta(minutes=1)
    ).all():
        raise ValueError("Noncontiguous candles")

    if not data["Close"].map(
        lambda x: math.isfinite(float(x)) and float(x) > 0
    ).all():
        raise ValueError("Invalid candle prices")

    folds = report["folds"]
    all_trades = report["test_trades"]

    verified = []
    errors = []
    expected_trades = []

    previous_entry = None
    previous_expiry = None

    for fold_number, fold in enumerate(folds, 1):
        test = fold["test"]
        start = fold["test_start"]
        end = fold["test_end"]

        if (
            type(start) is not int
            or type(end) is not int
            or not 0 <= start < end <= len(data)
        ):
            errors.append({
                "fold": fold_number,
                "problem": "INVALID_FOLD_BOUNDARY",
            })
            continue

        if test is None:
            if fold["selected"] is not None:
                errors.append({
                    "fold": fold_number,
                    "problem": "SELECTED_STRATEGY_WITHOUT_TEST",
                })
            continue

        trades = test["trades"]
        expected_trades.extend(trades)

        for index, trade in enumerate(trades, 1):
            problems = []

            i = trade["signal_index"]
            j = trade["expiry_index"]
            direction = trade["signal"]

            if type(i) is not int or type(j) is not int:
                problems.append("INVALID_INDEX")
                errors.append({
                    "fold": fold_number,
                    "trade": index,
                    "problems": problems,
                })
                continue

            if not (0 <= i < len(data) and 0 <= j < len(data)):
                problems.append("CANDLE_INDEX_OUT_OF_RANGE")
                errors.append({
                    "fold": fold_number,
                    "trade": index,
                    "problems": problems,
                })
                continue

            if not (start <= i and j < end):
                problems.append("FOLD_BOUNDARY_LEAKAGE")

            if j - i != EXPIRY:
                problems.append("WRONG_EXPIRY_INDEX")

            entry_time = data["timestamp"].iloc[i]
            exit_time = data["timestamp"].iloc[j]

            if exit_time - entry_time != timedelta(minutes=15):
                problems.append("WRONG_EXPIRY_TIME")

            if trade["signal_time"] != entry_time.isoformat():
                problems.append("SIGNAL_TIME_MISMATCH")

            entry = float(data["Close"].iloc[i])
            exit_price = float(data["Close"].iloc[j])

            if abs(float(trade["entry"]) - entry) > PRICE_TOLERANCE:
                problems.append("ENTRY_PRICE_MISMATCH")

            if abs(float(trade["exit"]) - exit_price) > PRICE_TOLERANCE:
                problems.append("EXIT_PRICE_MISMATCH")

            if direction not in ("UP", "DOWN"):
                problems.append("INVALID_DIRECTION")
                outcome = None
                pnl = None
            elif abs(entry - exit_price) <= PRICE_TOLERANCE:
                outcome = "PUSH"
                pnl = 0.0
            elif (
                (direction == "UP" and exit_price > entry)
                or (direction == "DOWN" and exit_price < entry)
            ):
                outcome = "WIN"
                pnl = payout
            else:
                outcome = "LOSS"
                pnl = -1.0

            if trade["result"] != outcome:
                problems.append("OUTCOME_MISMATCH")

            if previous_entry is not None and i <= previous_entry:
                problems.append("NON_CHRONOLOGICAL_TRADES")

            if previous_expiry is not None and i < previous_expiry:
                problems.append("OVERLAPPING_TRADES")

            previous_entry = i
            previous_expiry = j

            if problems:
                errors.append({
                    "fold": fold_number,
                    "trade": index,
                    "problems": sorted(set(problems)),
                })
            else:
                verified.append({
                    "fold": fold_number,
                    "entry_index": i,
                    "expiry_index": j,
                    "outcome": outcome,
                    "pnl": pnl,
                })

    # Ensure the aggregate does not omit or introduce trades.
    if expected_trades != all_trades:
        errors.append({
            "problem": "AGGREGATE_TRADE_LIST_MISMATCH"
        })

    if errors:
        return {
            "status": "BLOCKED_MISMATCH",
            "errors": errors,
            "metrics": None,
            "dataset_origin_verified": False,
            "forward_accuracy_proven": False,
        }

    wins = sum(t["outcome"] == "WIN" for t in verified)
    losses = sum(t["outcome"] == "LOSS" for t in verified)
    pushes = sum(t["outcome"] == "PUSH" for t in verified)
    resolved = wins + losses

    net = sum(t["pnl"] for t in verified)

    running = 0.0
    peak = 0.0
    drawdown = 0.0

    for trade in verified:
        running += trade["pnl"]
        peak = max(peak, running)
        drawdown = max(drawdown, peak - running)

    return {
        "status": "OFFLINE_RECONCILED",
        "errors": [],
        "dataset_origin_verified": False,
        "forward_accuracy_proven": False,
        "metrics": {
            "folds": len(folds),
            "total_trades": len(verified),
            "wins": wins,
            "losses": losses,
            "pushes": pushes,
            "resolved": resolved,
            "win_rate_percent": (
                round(100 * wins / resolved, 4)
                if resolved else None
            ),
            "break_even_win_rate_percent": round(
                100 / (1 + payout), 4
            ),
            "net_units": round(net, 6),
            "max_drawdown_units": round(drawdown, 6),
        },
    }


def run(
    csv_path=DEFAULT_CSV,
    initial_train=720,
    test_size=180,
    payout=0.8,
    min_training_trades=30,
):
    # Independent structural check before research replay.
    raw = parse_candles(csv_path)
    if not quality(raw)["continuous_one_minute_candles"]:
        raise ValueError("Historical CSV quality check failed")

    candles = load_candles(str(csv_path))

    if len(candles) != len(raw):
        raise ValueError("Loader changed candle count")

    for i, row in enumerate(raw):
        if (
            candles["timestamp"].iloc[i].to_pydatetime()
            != row["timestamp"]
            or abs(float(candles["Close"].iloc[i]) - row["close"])
            > PRICE_TOLERANCE
        ):
            raise ValueError("Loader differs from original CSV")

    source = walk_forward(
        candles,
        initial_train=initial_train,
        test_size=test_size,
        payout=payout,
        min_training_trades=min_training_trades,
    )

    result = audit_walk_forward(candles, source, payout=payout)
    return {
        "stage": 46,
        "audit_type": "STAGE36_WALK_FORWARD",
        "dataset_sha256": sha256_file(csv_path),
        "configuration": {
            "initial_train": initial_train,
            "test_size": test_size,
            "payout": payout,
            "min_training_trades": min_training_trades,
            "expiry_minutes": 15,
        },
        **result,
        "analysis_only": True,
        "execution_enabled": False,
        "api_requests_executed": 0,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "action", nargs="?", choices=("audit", "export"),
        default="audit"
    )
    parser.add_argument("--csv", type=Path, default=DEFAULT_CSV)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()

    try:
        result = run(csv_path=args.csv)
        print("=== STAGE 46 WALK-FORWARD RECONCILIATION ===")
        print(json.dumps(result, indent=2))

        if args.action == "export":
            path, created = write_evidence_report(result, args.out)
            print("report_path:", path)
            print("new_report_created:", created)

    except (OSError, ValueError, TypeError, KeyError) as exc:
        parser.exit(
            1, f"BLOCKED: {type(exc).__name__}: {exc}\n"
        )

    print("API calls: 0")
    print("Trading execution: DISABLED")


if __name__ == "__main__":
    main()
