"""Chronological walk-forward research evaluation."""

from pathlib import Path
from collections import Counter
import pandas as pd

from research.stage29_backtest import load_candles
from strategy.strategy_v3 import evaluate_v3

folder = Path(
    "data/research/prospective_accuracy/captures"
)

files = sorted(folder.glob("*.csv"))

if not files:
    raise SystemExit("No saved market captures")

df = pd.concat(
    [load_candles(p) for p in files],
    ignore_index=True
)

cols = ["Open", "High", "Low", "Close"]

if (
    df.groupby("timestamp")[cols].nunique() > 1
).any().any():
    raise SystemExit("Conflicting duplicate prices")

df = df.drop_duplicates("timestamp")
df = df.sort_values("timestamp")

# Exclude unverified weekend data.
df = df[df.timestamp.dt.day_of_week < 5].copy()

df["segment"] = (
    df.timestamp.diff() != pd.Timedelta(minutes=1)
).cumsum()

scores = Counter()
reasons = Counter()

print("===== STRATEGY V3 WALK-FORWARD =====")
print("Unique weekday candles:", len(df))

for _, segment in df.groupby("segment"):
    segment = segment.reset_index(drop=True)

    print("Continuous segment:", len(segment))

    # 195 completed candles for warmup.
    # Fixed rules; no fitting on future candles.
    # Non-overlapping 15-minute outcomes.

    for i in range(194, len(segment) - 15, 15):

        prefix = segment.iloc[:i + 1].copy()

        result = evaluate_v3(
            prefix,
            data_mode="live",
            data_quality_status="VALID"
        )

        signal = result["research_hypothesis"]
        reasons[result["reason"]] += 1

        entry = float(segment.Close.iloc[i])
        exit_price = float(segment.Close.iloc[i + 15])

        if signal == "NO TRADE":
            outcome = "NO TRADE"
        elif entry == exit_price:
            outcome = "PUSH"
        elif (exit_price > entry) == (signal == "UP"):
            outcome = "WIN"
        else:
            outcome = "LOSS"

        scores[outcome] += 1

        print(
            segment.timestamp.iloc[i],
            signal,
            outcome,
            result["market_regime"],
            result["reason"]
        )

wins = scores["WIN"]
losses = scores["LOSS"]
total = wins + losses

print("\n===== FINAL V3 REPORT =====")
print("RESULTS:", dict(scores))
print("REJECTION REASONS:", dict(reasons))
print("DIRECTIONAL OUTCOMES:", total)

print(
    "WIN RATE:",
    round(100 * wins / total, 2) if total else "N/A"
)

print(
    "NET UNITS AT 80% PAYOUT:",
    round(wins * 0.8 - losses, 2)
)

print("BREAK-EVEN WIN RATE: 55.56%")

if total < 100:
    print("VALIDATION: INSUFFICIENT OUTCOMES")
else:
    print("VALIDATION: FURTHER INDEPENDENT REVIEW REQUIRED")

print("API REQUESTS: 0")
print("BROKER ORDERS: 0")
print("EXECUTION ENABLED: False")
print("REAL-MONEY READINESS: NOT VERIFIED")
