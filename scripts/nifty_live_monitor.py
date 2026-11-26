import os
import time
import sqlite3
import requests
import joblib
import numpy as np
import pandas as pd
from pathlib import Path

ROOT = Path("data/research/nifty50/live")
ROOT.mkdir(parents=True, exist_ok=True)

token = os.environ.get("UPSTOX_ACCESS_TOKEN")
if not token:
    raise SystemExit("UPSTOX_ACCESS_TOKEN missing")

URL = (
    "https://api.upstox.com/v3/historical-candle/"
    "intraday/NSE_INDEX%7CNifty%2050/minutes/1"
)

HEADERS = {
    "Authorization": f"Bearer {token}",
    "Accept": "application/json"
}

models = {
    h: joblib.load(f"models/nifty50/live/research_{h}m.joblib")
    for h in [5, 10, 15]
}

db = sqlite3.connect(ROOT / "predictions.db")
db.execute("""
CREATE TABLE IF NOT EXISTS predictions (
    timestamp TEXT,
    horizon INTEGER,
    expiry TEXT,
    entry REAL,
    direction TEXT,
    up_score REAL,
    actual TEXT,
    exit_price REAL,
    result TEXT DEFAULT 'PENDING',
    PRIMARY KEY(timestamp, horizon)
)
""")
db.commit()

def fetch():
    r = requests.get(URL, headers=HEADERS, timeout=30)
    r.raise_for_status()
    payload = r.json()

    if payload.get("status") != "success":
        raise ValueError("Provider response unsuccessful")

    d = pd.DataFrame(
        payload["data"]["candles"],
        columns=[
            "timestamp", "Open", "High",
            "Low", "Close", "Volume", "OI"
        ]
    )

    d.timestamp = pd.to_datetime(d.timestamp, utc=True)
    d = d.sort_values("timestamp").drop_duplicates("timestamp")

    now = pd.Timestamp.now(tz="UTC")
    d = d[d.timestamp + pd.Timedelta(minutes=1) <= now]

    if d.empty:
        return d.set_index("timestamp")

    ohlc = ["Open", "High", "Low", "Close"]
    d[ohlc] = d[ohlc].apply(pd.to_numeric, errors="raise")

    if not np.isfinite(d[ohlc]).all().all():
        raise ValueError("Invalid OHLC")

    if not (
        (d.Low > 0)
        & (d.High >= d[["Open","Close","Low"]].max(axis=1))
        & (d.Low <= d[["Open","Close"]].min(axis=1))
    ).all():
        raise ValueError("Invalid candle structure")

    return d.set_index("timestamp")

def features(d):
    p = d.Close
    segment = (
        d.index.to_series().diff()
        != pd.Timedelta(minutes=1)
    ).cumsum()

    X = pd.DataFrame(index=d.index)

    for n in [1,3,5,10,15,30,60]:
        X[f"return_{n}"] = p.groupby(segment).pct_change(n)

    for n in [10,20,50]:
        X[f"ema_{n}"] = p / p.groupby(segment).transform(
            lambda s: s.ewm(
                span=n, adjust=False, min_periods=n
            ).mean()
        ) - 1

        X[f"volatility_{n}"] = p.groupby(segment).transform(
            lambda s: s.pct_change().rolling(n).std()
        )

    X["range"] = (d.High-d.Low)/p
    X["body"] = (p-d.Open)/d.Open

    local = d.index.tz_convert("Asia/Kolkata")
    X["minute"] = local.hour*60 + local.minute

    return X.replace([np.inf,-np.inf],np.nan)

def settle(d):
    rows = db.execute("""
        SELECT timestamp,horizon,expiry,entry,direction
        FROM predictions WHERE result='PENDING'
    """).fetchall()

    for ts,h,expiry,entry,direction in rows:
        target = pd.Timestamp(expiry)

        if target not in d.index:
            continue

        exit_price = float(d.loc[target,"Close"])

        actual = (
            "UP" if exit_price > entry
            else "DOWN" if exit_price < entry
            else "FLAT"
        )

        result = (
            "PUSH" if actual == "FLAT"
            else "WIN" if actual == direction
            else "LOSS"
        )

        db.execute("""
            UPDATE predictions
            SET actual=?,exit_price=?,result=?
            WHERE timestamp=? AND horizon=?
        """,(actual,exit_price,result,ts,h))

    db.commit()

def report():
    df = pd.read_sql_query(
        "SELECT * FROM predictions", db
    )
    df.to_csv(ROOT / "prediction_history.csv", index=False)

    for h in [5,10,15]:
        r = df[df.horizon == h]
        w = int((r.result == "WIN").sum())
        l = int((r.result == "LOSS").sum())
        pending = int((r.result == "PENDING").sum())

        accuracy = (
            round(100*w/(w+l),2)
            if w+l else "NOT VERIFIED"
        )

        print(
            f"{h}m | WIN={w} LOSS={l} "
            f"PENDING={pending} ACCURACY={accuracy}"
        )

print("===== NIFTY 24/7 MONITOR STARTED =====", flush=True)

while True:
    try:
        now = pd.Timestamp.now(tz="Asia/Kolkata")
        minute = now.hour*60 + now.minute

        if now.weekday() >= 5 or not 555 <= minute <= 935:
            print(
                now, "MARKET CLOSED / STANDBY",
                flush=True
            )
            time.sleep(60)
            continue

        d = fetch()

        if d.empty:
            time.sleep(60)
            continue

        d.to_csv(ROOT / "latest.csv")
        settle(d)

        latest = d.index[-1]
        age = (
            pd.Timestamp.now(tz="UTC")
            - latest
            - pd.Timedelta(minutes=1)
        ).total_seconds()

        X = features(d)

        print("\n===== MARKET UPDATE =====")
        print("TIME:", now)
        print("PRICE:", d.Close.iloc[-1])

        if not 0 <= age <= 120:
            print("STALE DATA: Prediction skipped")

        elif X.iloc[-1].isna().any():
            print("WARMUP: Waiting for sufficient candles")

        else:
            for h,model in models.items():
                expiry = latest + pd.Timedelta(minutes=h)
                local_expiry = expiry.tz_convert("Asia/Kolkata")

                if local_expiry.hour*60 + local_expiry.minute >= 930:
                    continue

                prior = db.execute("""
                    SELECT MAX(expiry) FROM predictions
                    WHERE horizon=?
                """,(h,)).fetchone()[0]

                if prior and latest < pd.Timestamp(prior):
                    continue

                row = X.iloc[[-1]][model.feature_name_]
                p = float(model.predict_proba(row)[0,1])
                direction = "UP" if p >= 0.5 else "DOWN"

                db.execute("""
                    INSERT OR IGNORE INTO predictions
                    (timestamp,horizon,expiry,entry,direction,up_score)
                    VALUES (?,?,?,?,?,?)
                """,(
                    latest.isoformat(),h,expiry.isoformat(),
                    float(d.Close.iloc[-1]),direction,p
                ))

                print(
                    f"{h}m | {direction} | "
                    f"UP={p*100:.2f}% | "
                    f"DOWN={(1-p)*100:.2f}%"
                )

            db.commit()

        report()
        print("MODE: PAPER RESEARCH", flush=True)

    except Exception as e:
        print("MONITOR ERROR:", type(e).__name__, flush=True)

    time.sleep(60)
