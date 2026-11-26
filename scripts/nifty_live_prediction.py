import os
import requests
import pandas as pd
import numpy as np
import joblib
from pathlib import Path
from lightgbm import LGBMClassifier
from sklearn.metrics import accuracy_score

ROOT = Path("data/research/nifty50")
OUT = Path("models/nifty50/live")
OUT.mkdir(parents=True, exist_ok=True)

token = os.environ["UPSTOX_ACCESS_TOKEN"]

r = requests.get(
    "https://api.upstox.com/v3/historical-candle/intraday/NSE_INDEX%7CNifty%2050/minutes/1",
    headers={
        "Authorization": f"Bearer {token}",
        "Accept": "application/json"
    },
    timeout=30
)
r.raise_for_status()

cols = ["timestamp","Open","High","Low","Close","Volume","OI"]

live = pd.DataFrame(r.json()["data"]["candles"], columns=cols)
live.timestamp = pd.to_datetime(live.timestamp, utc=True)

now = pd.Timestamp.now(tz="UTC")
live = live[live.timestamp + pd.Timedelta(minutes=1) <= now]

if live.empty:
    raise SystemExit("No completed market candles")

hist = pd.read_csv(ROOT / "historical.csv")
hist.timestamp = pd.to_datetime(hist.timestamp, utc=True)

d = pd.concat([hist, live], ignore_index=True)
d = d.sort_values("timestamp").drop_duplicates("timestamp", keep="last")
d = d.set_index("timestamp")

for c in ["Open","High","Low","Close"]:
    d[c] = pd.to_numeric(d[c], errors="raise")

assert np.isfinite(d[["Open","High","Low","Close"]]).all().all()
assert (d.Low > 0).all()
assert (d.High >= d[["Open","Close","Low"]].max(axis=1)).all()
assert (d.Low <= d[["Open","Close"]].min(axis=1)).all()

p = d.Close
session = d.index.tz_convert("Asia/Kolkata").date
segment = (
    d.index.to_series().diff() != pd.Timedelta(minutes=1)
).cumsum()

X = pd.DataFrame(index=d.index)

for n in [1,3,5,10,15,30,60]:
    X[f"return_{n}"] = p.groupby(segment).pct_change(n)

for n in [10,20,50]:
    X[f"ema_{n}"] = p / p.groupby(segment).transform(
        lambda s: s.ewm(span=n, adjust=False, min_periods=n).mean()
    ) - 1

    X[f"volatility_{n}"] = p.groupby(segment).transform(
        lambda s: s.pct_change().rolling(n).std()
    )

X["range"] = (d.High-d.Low)/p
X["body"] = (p-d.Open)/d.Open

local = d.index.tz_convert("Asia/Kolkata")
X["minute"] = local.hour*60 + local.minute
X = X.replace([np.inf,-np.inf],np.nan)

latest = live.timestamp.max()
age = (now-latest-pd.Timedelta(minutes=1)).total_seconds()

print("===== NIFTY 50 PREDICTION ENGINE =====")
print("SOURCE: UPSTOX")
print("TOTAL CANDLES:", len(d))
print("LATEST PRICE:", p.loc[latest])
print("LATEST CANDLE:", latest.tz_convert("Asia/Kolkata"))
print("DATA FRESH:", 0 <= age <= 120)

if X.loc[latest].isna().any():
    raise SystemExit("Insufficient contiguous candles for prediction")

for h in [5,10,15]:
    future = p.groupby(segment).shift(-h)
    valid = X.notna().all(axis=1) & future.notna() & future.ne(p)

    x = X.loc[valid]
    y = (future.loc[valid] > p.loc[valid]).astype(int)

    split = int(len(x)*0.8)
    test = x.iloc[split:]
    cutoff = test.index[0]-pd.Timedelta(minutes=h)
    train = x.loc[x.index < cutoff]

    model = LGBMClassifier(
        n_estimators=200,
        learning_rate=0.025,
        num_leaves=15,
        min_child_samples=100,
        reg_lambda=5,
        random_state=42,
        verbosity=-1,
        n_jobs=4
    )

    model.fit(train, y.loc[train.index])
    pred = model.predict(test)

    acc = accuracy_score(y.loc[test.index], pred)
    majority = int(y.loc[train.index].mean() >= 0.5)
    baseline = (y.loc[test.index] == majority).mean()

    eligible = x.index + pd.Timedelta(minutes=h) <= latest
    full = x.loc[eligible]

    model.fit(full, y.loc[full.index])
    prob = model.predict_proba(X.loc[[latest]])[0,1]

    joblib.dump(model, OUT / f"research_{h}m.joblib")

    print(f"\n===== {h} MINUTE =====")
    print("MODEL DIRECTION:", "UP" if prob >= 0.5 else "DOWN")
    print("UP SCORE:", round(prob*100,2))
    print("DOWN SCORE:", round((1-prob)*100,2))
    print("HISTORICAL ACCURACY:", round(acc*100,2))
    print("BASELINE ACCURACY:", round(baseline*100,2))
    print("STATUS:", "RESEARCH_ONLY" if 0 <= age <= 120 else "STALE_DATA")
    print("TRADE APPROVED: FALSE")

print("\nBROKER ORDERS: 0")
print("PREDICTION ENGINE COMPLETE")
