import os
import json
import getpass
from pathlib import Path

import requests
import numpy as np
import pandas as pd
import joblib

from xgboost import XGBClassifier
from lightgbm import LGBMClassifier
from sklearn.metrics import accuracy_score

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

KEY = (
    os.getenv("TWELVE_DATA_API_KEY")
    or os.getenv("TWELVEDATA_API_KEY")
)

if not KEY:
    KEY = getpass.getpass("Twelve Data API key: ")

OUT = Path("data/research/twelve_live")
OUT.mkdir(parents=True, exist_ok=True)

print("===== TWELVE DATA ML ENGINE =====")

# Discover Nifty 50 instrument
r = requests.get(
    "https://api.twelvedata.com/symbol_search",
    params={
        "symbol": "NIFTY 50",
        "apikey": KEY
    },
    timeout=30
)
r.raise_for_status()
items = r.json().get("data", [])

matches = [
    x for x in items
    if x.get("country", "").lower() == "india"
    and "nifty 50" in x.get(
        "instrument_name", ""
    ).lower()
    and x.get("instrument_type", "").lower() == "index"
]

if not matches:
    raise SystemExit(
        "Nifty 50 index not found. "
        "Check Twelve Data instrument coverage."
    )

instrument = matches[0]
symbol = instrument["symbol"]
exchange = instrument.get("exchange", "NSE")

print("SYMBOL:", symbol)
print("EXCHANGE:", exchange)

# Fresh real market data
r = requests.get(
    "https://api.twelvedata.com/time_series",
    params={
        "symbol": symbol,
        "exchange": exchange,
        "interval": "1min",
        "outputsize": 5000,
        "timezone": "UTC",
        "apikey": KEY
    },
    timeout=60
)
r.raise_for_status()
payload = r.json()

if "values" not in payload:
    raise SystemExit(
        payload.get("message", "API data unavailable")
    )

d = pd.DataFrame(payload["values"])
d["timestamp"] = pd.to_datetime(
    d["datetime"], utc=True
)

for c in ["open", "high", "low", "close"]:
    d[c] = pd.to_numeric(d[c], errors="raise")

now = pd.Timestamp.now(tz="UTC")

d = d[
    d.timestamp + pd.Timedelta(minutes=1) <= now
].sort_values("timestamp")

if d.timestamp.duplicated().any():
    raise SystemExit("Duplicate timestamps")

if (
    not np.isfinite(
        d[["open","high","low","close"]]
    ).all().all()
    or (d[["open","high","low","close"]] <= 0).any().any()
    or (d.high < d[["open","close","low"]].max(axis=1)).any()
    or (d.low > d[["open","close","high"]].min(axis=1)).any()
):
    raise SystemExit("Invalid market candles")

local = d.timestamp.dt.tz_convert("Asia/Kolkata")
minute = local.dt.hour * 60 + local.dt.minute
d = d[(minute >= 555) & (minute < 930)].copy()

if len(d) < 2000:
    raise SystemExit("Insufficient API candles")

d.to_csv(OUT/"fresh_candles.csv", index=False)

print("REAL API CANDLES:", len(d))
print("LATEST CANDLE:", d.timestamp.max())

d["segment"] = (
    d.timestamp.diff() != pd.Timedelta(minutes=1)
).cumsum()

def build(g):
    g = g.copy()
    c = g.close

    for n in [1,3,5,10,15,30]:
        g[f"ret_{n}"] = c.pct_change(n)

    for n in [9,20,50]:
        g[f"ema_{n}"] = (
            c/c.ewm(span=n, adjust=False).mean()-1
        )

    delta = c.diff()
    gain = delta.clip(lower=0).rolling(14).mean()
    loss = (-delta.clip(upper=0)).rolling(14).mean()

    g["rsi"] = 100-100/(1+gain/loss.clip(lower=1e-10))
    g["atr"] = (g.high-g.low).rolling(14).mean()/c
    g["volatility"] = c.pct_change().rolling(20).std()
    g["body"] = (c-g.open)/c
    g["momentum"] = c.pct_change(20)

    for h in [5,10,15]:
        g[f"future_{h}"] = c.shift(-h)/c-1

    return g

raw = set(d.columns)

d = pd.concat([
    build(g) for _,g in d.groupby("segment")
], ignore_index=True)

features = [
    c for c in d.columns
    if c not in raw
    and not c.startswith("future_")
]

d = d.replace([np.inf,-np.inf],np.nan)
latest = d.tail(1)

if latest[features].isna().any().any():
    raise SystemExit("Latest session needs more candles")

report = {}

for h in [5,10,15]:

    target = f"future_{h}"
    z = d.dropna(subset=features+[target])

    if len(z) < 1000:
        raise SystemExit("Insufficient training samples")

    X = z[features]
    y = (z[target]>0).astype(int)

    split = int(len(z)*0.80)
    gap = h+1

    models = [
        XGBClassifier(
            n_estimators=150,
            max_depth=3,
            learning_rate=0.03,
            n_jobs=2,
            random_state=42
        ),
        LGBMClassifier(
            n_estimators=150,
            max_depth=4,
            learning_rate=0.03,
            n_jobs=2,
            random_state=42,
            verbosity=-1
        )
    ]

    for m in models:
        m.fit(
            X.iloc[:split-gap],
            y.iloc[:split-gap]
        )

    p = np.mean([
        m.predict_proba(X.iloc[split:])[:,1]
        for m in models
    ], axis=0)

    accuracy = accuracy_score(
        y.iloc[split:], p>=0.5
    )

    baseline = max(
        y.iloc[split:].mean(),
        1-y.iloc[split:].mean()
    )

    prob = float(np.mean([
        m.predict_proba(latest[features])[0,1]
        for m in models
    ]))

    age = (
        now-latest.timestamp.iloc[0]
        -pd.Timedelta(minutes=1)
    ).total_seconds()

    result = {
        "expiry_minutes": h,
        "direction": "UP" if prob>=0.5 else "DOWN",
        "up_model_score_pct": round(prob*100,2),
        "down_model_score_pct": round((1-prob)*100,2),
        "historical_accuracy_pct": round(accuracy*100,2),
        "baseline_pct": round(baseline*100,2),
        "data_timestamp": str(latest.timestamp.iloc[0]),
        "data_age_seconds": round(age),
        "stale_data": age>120,
        "status": "UNVERIFIED_RESEARCH",
        "trade_approved": False
    }

    report[str(h)] = result

    joblib.dump({
        "models":models,
        "features":features,
        "execution_enabled":False
    }, OUT/f"model_{h}m.joblib")

    print(json.dumps(result,indent=2))

(OUT/"report.json").write_text(
    json.dumps(report,indent=2)
)

print("===== TRAINING COMPLETE =====")
print("PROVIDER: TWELVE DATA")
print("BROKER ORDERS: 0")
print("REPORT:", OUT/"report.json")
