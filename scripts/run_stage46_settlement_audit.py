"""Stage 46: independent offline audit of 15-minute trade settlements.

Requires an existing, authentic trade ledger. Never creates signals,
rewrites trades, calls a provider, or executes orders.

Timestamp convention: entry_time and expiry_time are candle CLOSE
timestamps; settlement is exactly 15 minutes after entry.
"""
import argparse
import csv
import json
import math
from collections import Counter
from datetime import timedelta
from pathlib import Path

from scripts.run_stage45_dataset_audit import (
    parse_candles,
    quality,
)
from scripts.run_stage41_evidence_audit import (
    sha256_file,
    write_evidence_report,
)

CANDLES = Path("data/historical/eurusd_1min_1day.csv")
TRADES = Path("data/research/stage46/trades.csv")
OUT = Path("data/research/stage46/reports")
EXPIRY = timedelta(minutes=15)
PRICE_TOLERANCE = 1e-10
PNL_TOLERANCE = 1e-8

REQUIRED = {
    "trade_id", "entry_time", "direction", "entry_price",
    "expiry_time", "exit_price", "partition", "result",
    "profit_loss",
}


def number(value, label):
    try:
        value = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid {label}") from exc

    if not math.isfinite(value):
        raise ValueError(f"Nonfinite {label}")
    return value


def parse_trades(path):
    """Read recorded trades; never silently fill missing trade fields."""
    from scripts.run_stage45_dataset_audit import parse_timestamp

    with Path(path).open(
        newline="", encoding="utf-8-sig"
    ) as handle:
        reader = csv.DictReader(handle)

        if not reader.fieldnames:
            raise ValueError("Trade ledger header missing")
        if len(reader.fieldnames) != len(set(reader.fieldnames)):
            raise ValueError("Duplicate trade-ledger columns")
        if not REQUIRED.issubset(set(reader.fieldnames)):
            missing = sorted(REQUIRED - set(reader.fieldnames))
            raise ValueError(f"Missing trade-ledger columns: {missing}")

        trades = []
        for line, row in enumerate(reader, 2):
            try:
                if any(row.get(k) in (None, "") for k in REQUIRED):
                    raise ValueError("Missing trade field")

                trade = {
                    "trade_id": row["trade_id"].strip(),
                    "entry_time": parse_timestamp(row["entry_time"]),
                    "direction": row["direction"].strip().upper(),
                    "entry_price": number(
                        row["entry_price"], "entry_price"
                    ),
                    "expiry_time": parse_timestamp(row["expiry_time"]),
                    "exit_price": number(
                        row["exit_price"], "exit_price"
                    ),
                    "partition": row["partition"].strip().upper(),
                    "result": row["result"].strip().upper(),
                    "profit_loss": number(
                        row["profit_loss"], "profit_loss"
                    ),
                }
                if not trade["trade_id"]:
                    raise ValueError("Empty trade ID")
                trades.append(trade)
            except (ValueError, TypeError, KeyError) as exc:
                raise ValueError(
                    f"Invalid trade ledger row {line}: {exc}"
                ) from exc

    return trades


def expected_result(direction, entry, exit_price, payout):
    difference = exit_price - entry

    if abs(difference) <= PRICE_TOLERANCE:
        return "PUSH", 0.0

    is_win = (
        (direction == "UP" and difference > 0)
        or (direction == "DOWN" and difference < 0)
    )

    return ("WIN", payout) if is_win else ("LOSS", -1.0)


def assess(candle_path=CANDLES, ledger_path=TRADES, payout=0.8):
    """Return fail-closed audit. A failed trade invalidates all metrics."""
    if not 0 < payout <= 1:
        raise ValueError("Payout must be within (0, 1]")

    rows = parse_candles(candle_path)
    candle_quality = quality(rows)
    if not candle_quality["continuous_one_minute_candles"]:
        raise ValueError("Candle continuity/ordering check failed")

    if len(rows) < 32:
        raise ValueError("Insufficient candles for audit")

    candle_map = {r["timestamp"]: r for r in rows}
    boundary = int(len(rows) * 0.8)
    training_end = rows[boundary - 1]["timestamp"]
    holdout_start = rows[boundary]["timestamp"]

    report = {
        "stage": 46,
        "candles_sha256": sha256_file(candle_path),
        "dataset_origin_verified": False,
        "feed_mode": "UNKNOWN",
        "ledger_available": Path(ledger_path).is_file(),
        "ledger_sha256": (
            sha256_file(ledger_path)
            if Path(ledger_path).is_file() else None
        ),
        "training_last_close_utc": training_end.isoformat(),
        "holdout_first_close_utc": holdout_start.isoformat(),
        "expiry_minutes": 15,
        "payout_assumption": payout,
        "stake_per_trade_units": 1.0,
        "status": "BLOCKED",
        "errors": [],
        "metrics": None,
        "forward_accuracy_proven": False,
        "directional_signals_authorized": False,
        "analysis_only": True,
        "execution_enabled": False,
        "api_requests_executed": 0,
    }

    if not Path(ledger_path).is_file():
        report["errors"].append("TRADE_LEDGER_NOT_PROVIDED")
        return report

    trades = parse_trades(ledger_path)

    if not trades:
        report["errors"].append("TRADE_LEDGER_EMPTY")
        return report

    previous_entry = None
    previous_expiry = None
    trade_ids = set()
    recalculated = []

    for i, trade in enumerate(trades, 1):
        problems = []
        entry_time = trade["entry_time"]
        expiry_time = trade["expiry_time"]
        direction = trade["direction"]
        partition = trade["partition"]

        if trade["trade_id"] in trade_ids:
            problems.append("DUPLICATE_TRADE_ID")
        trade_ids.add(trade["trade_id"])

        if direction not in ("UP", "DOWN"):
            problems.append("INVALID_DIRECTION")

        if partition not in ("TRAINING", "HOLDOUT"):
            problems.append("INVALID_PARTITION")

        if expiry_time - entry_time != EXPIRY:
            problems.append("WRONG_EXPIRY")

        if previous_entry is not None and entry_time <= previous_entry:
            problems.append("NON_CHRONOLOGICAL_ENTRIES")

        if previous_expiry is not None and entry_time < previous_expiry:
            problems.append("OVERLAPPING_TRADES")

        previous_entry = entry_time
        previous_expiry = expiry_time

        entry_candle = candle_map.get(entry_time)
        expiry_candle = candle_map.get(expiry_time)

        if entry_candle is None:
            problems.append("ENTRY_CANDLE_MISSING")
        if expiry_candle is None:
            problems.append("EXPIRY_CANDLE_MISSING")

        if entry_candle is not None and (
            abs(trade["entry_price"] - entry_candle["close"])
            > PRICE_TOLERANCE
        ):
            problems.append("ENTRY_PRICE_MISMATCH")

        if expiry_candle is not None and (
            abs(trade["exit_price"] - expiry_candle["close"])
            > PRICE_TOLERANCE
        ):
            problems.append("EXIT_PRICE_MISMATCH")

        if partition == "TRAINING" and (
            entry_time > training_end or expiry_time > training_end
        ):
            problems.append("TRAINING_HOLDOUT_LEAKAGE")

        if partition == "HOLDOUT" and entry_time < holdout_start:
            problems.append("HOLDOUT_ENTRY_BEFORE_SPLIT")

        if trade["entry_price"] <= 0 or trade["exit_price"] <= 0:
            problems.append("INVALID_TRADE_PRICE")

        if direction in ("UP", "DOWN") and (
            entry_candle is not None and expiry_candle is not None
        ):
            result, pnl = expected_result(
                direction, entry_candle["close"],
                expiry_candle["close"], payout
            )

            if trade["result"] != result:
                problems.append("RECORDED_OUTCOME_MISMATCH")

            if abs(trade["profit_loss"] - pnl) > PNL_TOLERANCE:
                problems.append("RECORDED_PNL_MISMATCH")

            if not problems:
                recalculated.append({
                    "result": result,
                    "profit_loss": pnl,
                    "partition": partition,
                })

        if problems:
            report["errors"].append({
                "trade_row": i,
                "trade_id": trade["trade_id"],
                "problems": sorted(set(problems)),
            })

    if report["errors"]:
        report["status"] = "BLOCKED_SETTLEMENT_MISMATCH"
        return report

    counts = Counter(t["result"] for t in recalculated)
    wins, losses, pushes = (
        counts["WIN"], counts["LOSS"], counts["PUSH"]
    )
    resolved = wins + losses

    balance = 0.0
    peak = 0.0
    max_drawdown = 0.0

    for trade in recalculated:
        balance += trade["profit_loss"]
        peak = max(peak, balance)
        max_drawdown = max(max_drawdown, peak - balance)

    by_partition = {}
    for partition in ("TRAINING", "HOLDOUT"):
        subset = [
            t for t in recalculated
            if t["partition"] == partition
        ]
        partition_counts = Counter(t["result"] for t in subset)
        p_wins = partition_counts["WIN"]
        p_losses = partition_counts["LOSS"]
        denominator = p_wins + p_losses

        by_partition[partition] = {
            "trades": len(subset),
            "wins": p_wins,
            "losses": p_losses,
            "pushes": partition_counts["PUSH"],
            "win_rate_percent": (
                round(100 * p_wins / denominator, 4)
                if denominator else None
            ),
            "net_units": round(
                sum(t["profit_loss"] for t in subset), 6
            ),
        }

    report["status"] = "OFFLINE_RECONCILED"
    report["metrics"] = {
        "total_trades": len(recalculated),
        "resolved_trades": resolved,
        "wins": wins,
        "losses": losses,
        "pushes": pushes,
        "win_rate_percent": (
            round(100 * wins / resolved, 4)
            if resolved else None
        ),
        "break_even_win_rate_percent": round(
            100 / (1 + payout), 4
        ),
        "net_units": round(balance, 6),
        "max_drawdown_units": round(max_drawdown, 6),
        "partitions": by_partition,
    }
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "action", nargs="?", choices=("audit", "export"),
        default="audit"
    )
    parser.add_argument("--candles", type=Path, default=CANDLES)
    parser.add_argument("--trades", type=Path, default=TRADES)
    parser.add_argument("--out", type=Path, default=OUT)
    args = parser.parse_args()

    try:
        result = assess(args.candles, args.trades)
        print("=== STAGE 46 OFFLINE SETTLEMENT AUDIT ===")
        print(json.dumps(result, indent=2))

        if args.action == "export":
            path, created = write_evidence_report(
                result, args.out
            )
            print("report_path:", path)
            print("new_report_created:", created)

    except (OSError, ValueError, KeyError, TypeError) as exc:
        parser.exit(
            1, f"BLOCKED: {type(exc).__name__}: {exc}\n"
        )

    print("API requests: 0")
    print("Real trading execution: DISABLED")


if __name__ == "__main__":
    main()
