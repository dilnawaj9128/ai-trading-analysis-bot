"""Offline backtest: no API calls, no trading. Run from repository root."""
import argparse
import csv
from pathlib import Path

from research.stage29_backtest import BacktestDataError, backtest, load_candles


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--csv", default="data/real_market/latest_eurusd_completed.csv")
    p.add_argument("--out", default="data/backtests/stage29_trades.csv")
    p.add_argument("--payout", type=float, default=0.8)
    args = p.parse_args()
    try:
        candles = load_candles(args.csv)
        report = backtest(candles, payout=args.payout)
    except (BacktestDataError, ValueError, KeyError, TypeError, ImportError) as exc:
        print("BACKTEST BLOCKED:", type(exc).__name__, str(exc))
        raise SystemExit(1)
    print("=== STAGE 29 OFFLINE 15-MIN BACKTEST ===")
    print("candles:", len(candles))
    print("method:", report["method"])
    for section in ("training", "holdout"):
        s = report[section]
        print(section.upper(), "trades:", s["signals"], "wins:", s["wins"],
              "losses:", s["losses"], "pushes:", s["pushes"],
              "no_trade:", s["no_trade"], "skipped:", s["skipped_windows"],
              "win_rate:", "N/A" if s["win_rate"] is None else f"{s['win_rate']:.2%}",
              "net_units:", s["net_units"])
    if report["holdout"]["resolved"] < 30:
        print("WARNING: Fewer than 30 resolved holdout signals; accuracy estimate is unreliable.")
    print("Assumptions: close-based idealized fill, 80% payout by default; no broker parity.")
    output = Path(args.out)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", newline="", encoding="utf8") as f:
        cols = ["partition", "signal_time_utc", "entry_time_utc", "exit_time_utc", "signal", "entry_close", "exit_close", "result"]
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(report["trades"])
    print("trade_log:", output)


if __name__ == "__main__":
    main()
