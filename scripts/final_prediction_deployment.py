import os
import json
import math
import urllib.request
import urllib.parse
from pathlib import Path
from collections import Counter
from datetime import datetime, timezone

import pandas as pd

from indicators import calculate_indicators
from patterns.candlestick import detect_candlestick_patterns
from research.stage29_backtest import existing_strategy_on_prefix
from strategy.strategy_v2 import evaluate
from strategy.strategy_v3 import evaluate_v3

ROOT = Path("data/research/final_validation")
ROOT.mkdir(parents=True, exist_ok=True)

CACHE = ROOT / "eurusd_5000.csv"
REPORT = ROOT / "final_report.json"

EXPIRY = 15
WARMUP = 195
PAYOUT = 0.80
MIN_OUTCOMES = 100

api_requests = 0

print("=" * 60)
print("FINAL AI PREDICTION ENGINE DEPLOYMENT")
print("=" * 60)


# ==================================================
# 1. HISTORICAL MARKET DATA
# ==================================================

if CACHE.exists():
    print("\n[1/6] Loading cached historical market data")
    df = pd.read_csv(CACHE)

else:
    print("\n[1/6] Fetching historical market data")

    key = os.getenv("TWELVE_DATA_API_KEY")

    if not key:
        raise SystemExit(
            "STOP: TWELVE_DATA_API_KEY not configured"
        )

    params = urllib.parse.urlencode({
        "symbol": "EUR/USD",
        "interval": "1min",
        "outputsize": 5000,
        "timezone": "UTC",
        "apikey": key
    })

    url = "https://api.twelvedata.com/time_series?" + params

    api_requests += 1

    try:
        with urllib.request.urlopen(url, timeout=30) as response:
            payload = json.loads(response.read())

    except Exception as exc:
        raise SystemExit(
            f"API request failed: {type(exc).__name__}"
        )

    if "values" not in payload:
        raise SystemExit(
            "Provider rejected request. "
            "Check plan, quota and API permissions."
        )

    df = pd.DataFrame(payload["values"])

    df = df.rename(columns={
        "datetime": "timestamp",
        "open": "Open",
        "high": "High",
        "low": "Low",
        "close": "Close"
    })


# ==================================================
# 2. DATA VALIDATION
# ==================================================

print("\n[2/6] Validating completed candles")

cols = ["Open", "High", "Low", "Close"]

df = df[["timestamp"] + cols].copy()

df["timestamp"] = pd.to_datetime(
    df["timestamp"], utc=True, errors="raise"
)

for col in cols:
    df[col] = pd.to_numeric(df[col], errors="raise")

if not df[cols].map(math.isfinite).all().all():
    raise SystemExit("STOP: Non-finite OHLC values")

if (df[cols] <= 0).any().any():
    raise SystemExit("STOP: Invalid prices")

if (
    (df.High < df[cols].max(axis=1)).any()
    or (df.Low > df[cols].min(axis=1)).any()
):
    raise SystemExit("STOP: Invalid OHLC structure")

if (
    df.groupby("timestamp")[cols].nunique() > 1
).any().any():
    raise SystemExit("STOP: Conflicting duplicates")

if not (
    df.timestamp == df.timestamp.dt.floor("min")
).all():
    raise SystemExit("STOP: Misaligned timestamps")

df = df.drop_duplicates("timestamp")
df = df.sort_values("timestamp")

now = pd.Timestamp.now(tz="UTC")

df = df[
    df.timestamp + pd.Timedelta(minutes=1) <= now
]

df = df[df.timestamp.dt.day_of_week < 5]

df = df.reset_index(drop=True)

if len(df) < 500:
    raise SystemExit("STOP: Insufficient historical data")

df.to_csv(CACHE, index=False)

df["segment"] = (
    df.timestamp.diff() != pd.Timedelta(minutes=1)
).cumsum()

print("Validated candles:", len(df))
print("Continuous segments:", df.segment.nunique())
print("First candle:", df.timestamp.iloc[0])
print("Last candle:", df.timestamp.iloc[-1])


# ==================================================
# 3. STRATEGY ENGINE
# ==================================================

print("\n[3/6] Loading V1, V2 and V3")

def strategy_v2(frame):
    enriched = calculate_indicators(frame.copy())

    patterns = detect_candlestick_patterns(
        frame.copy()
    )

    if "Pattern_Direction" in patterns.columns:
        enriched["Pattern_Direction"] = (
            patterns["Pattern_Direction"].to_numpy()
        )

    return evaluate(
        enriched,
        data_mode="live",
        data_quality_status="VALID"
    )["research_hypothesis"]


def strategy_v3(frame):
    return evaluate_v3(
        frame,
        data_mode="live",
        data_quality_status="VALID"
    )["research_hypothesis"]


strategies = {
    "V1": existing_strategy_on_prefix,
    "V2": strategy_v2,
    "V3": strategy_v3
}


# ==================================================
# 4. CHRONOLOGICAL COMPARISON
# ==================================================

print("\n[4/6] Running chronological comparison")

split = df.timestamp.iloc[int(len(df) * 0.70)]

scores = {
    phase: {
        name: Counter() for name in strategies
    }
    for phase in ("DEVELOPMENT", "HOLDOUT")
}

evaluated = 0

for _, segment in df.groupby("segment"):

    segment = segment.reset_index(drop=True)

    for i in range(
        WARMUP - 1,
        len(segment) - EXPIRY,
        EXPIRY
    ):

        entry_time = segment.timestamp.iloc[i]
        exit_time = segment.timestamp.iloc[i + EXPIRY]

        if exit_time < split:
            phase = "DEVELOPMENT"

        elif entry_time >= split:
            phase = "HOLDOUT"

        else:
            continue

        prefix = segment.iloc[:i + 1].copy()

        entry = float(segment.Close.iloc[i])

        exit_price = float(
            segment.Close.iloc[i + EXPIRY]
        )

        for name, fn in strategies.items():

            signal = fn(prefix.copy())

            if signal == "NO TRADE":
                outcome = "NO TRADE"

            elif signal not in ("UP", "DOWN"):
                raise ValueError(
                    f"Invalid signal from {name}"
                )

            elif exit_price == entry:
                outcome = "PUSH"

            elif (
                (exit_price > entry) == (signal == "UP")
            ):
                outcome = "WIN"

            else:
                outcome = "LOSS"

            scores[phase][name][outcome] += 1

        evaluated += 1

        if evaluated % 25 == 0:
            print("Evaluated windows:", evaluated)


# ==================================================
# 5. PERFORMANCE AND STRATEGY SELECTION
# ==================================================

print("\n[5/6] Generating performance report")

def metrics(score):

    wins = score["WIN"]
    losses = score["LOSS"]
    total = wins + losses

    rate = wins / total if total else 0

    # Wilson 95% lower confidence bound
    z = 1.96

    lower = (
        (
            rate + z*z/(2*total)
            - z * math.sqrt(
                rate*(1-rate)/total
                + z*z/(4*total*total)
            )
        ) / (1 + z*z/total)
        if total else 0
    )

    return {
        "wins": wins,
        "losses": losses,
        "pushes": score["PUSH"],
        "no_trade": score["NO TRADE"],
        "directional_outcomes": total,
        "win_rate_pct": round(rate * 100, 2)
            if total else None,
        "lower_confidence_pct": round(lower * 100, 2),
        "net_units": round(wins * PAYOUT - losses, 2)
    }


results = {
    phase: {
        name: metrics(score)
        for name, score in models.items()
    }
    for phase, models in scores.items()
}

for phase, models in results.items():

    print("\n==========", phase, "==========")

    for name, result in models.items():

        print("\nSTRATEGY:", name)

        for key, value in result.items():
            print(key.upper(), ":", value)


# Select candidate using development data only.

development = results["DEVELOPMENT"]

eligible = [
    name for name, result in development.items()
    if result["directional_outcomes"] >= 30
    and result["net_units"] > 0
]

candidate = (
    max(
        eligible,
        key=lambda name:
            development[name]["lower_confidence_pct"]
    )
    if eligible else None
)

break_even = 100 / (1 + PAYOUT)

status = "RESEARCH_ONLY"

if candidate:

    holdout = results["HOLDOUT"][candidate]

    if (
        holdout["directional_outcomes"] >= MIN_OUTCOMES
        and holdout["lower_confidence_pct"] > break_even
        and holdout["net_units"] > 0
    ):
        status = "CANDIDATE_FOR_FORWARD_VALIDATION"


# ==================================================
# 6. FINAL LOCAL DEPLOYMENT REPORT
# ==================================================

report = {
    "generated_at": datetime.now(
        timezone.utc
    ).isoformat(),
    "symbol": "EUR/USD",
    "expiry_minutes": EXPIRY,
    "historical_candles": len(df),
    "evaluated_windows": evaluated,
    "split_timestamp": str(split),
    "break_even_win_rate_pct": round(break_even, 2),
    "results": results,
    "research_candidate": candidate,
    "status": status,
    "api_requests": api_requests,
    "broker_orders": 0,
    "execution_enabled": False,
    "live_trading_signal": "NO TRADE",
    "real_money_ready": False
}

REPORT.write_text(
    json.dumps(report, indent=2)
)

print("\n" + "=" * 60)
print("FINAL DEPLOYMENT REPORT")
print("=" * 60)

print("STRATEGIES: V1, V2, V3")
print("MARKET: EUR/USD")
print("EXPIRY: 15 MINUTES")
print("HISTORICAL CANDLES:", len(df))
print("EVALUATED WINDOWS:", evaluated)
print("RESEARCH CANDIDATE:", candidate)
print("STATUS:", status)
print("API REQUESTS:", api_requests)
print("BROKER ORDERS: 0")
print("EXECUTION ENABLED: False")
print("REAL-MONEY READY: False")
print("REPORT SAVED:", REPORT)

print("\nLOCAL RESEARCH DEPLOYMENT COMPLETE")
