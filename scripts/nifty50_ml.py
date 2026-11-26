import os
import json
import getpass
from pathlib import Path
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import requests
import joblib

from xgboost import XGBClassifier
from lightgbm import LGBMClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import TimeSeriesSplit
from sklearn.metrics import accuracy_score, brier_score_loss

ROOT = Path("data/research/nifty50")
MODELS = Path("models/nifty50")
CACHE = ROOT / "historical.csv"

ROOT.mkdir(parents=True, exist_ok=True)
MODELS.mkdir(parents=True, exist_ok=True)

IST = ZoneInfo("Asia/Kolkata")

print("===== NIFTY 50 ML RESEARCH ENGINE =====")

# 1. Historical market data

if CACHE.exists():
    df = pd.read_csv(CACHE)
else:
    end = datetime.now(IST).date() - timedelta(days=1)
    rows = []

    base = (
        "https://api.upstox.com/v3/"
        "historical-candle/NSE_INDEX%7CNifty%2050/minutes/1"
    )

    token = os.getenv("UPSTOX_ACCESS_TOKEN", "")

    headers = {"Accept": "application/json"}

    if token:
        headers["Authorization"] = "Bearer " + token

    for batch in range(12):
        start = end - timedelta(days=27)
        url = f"{base}/{end}/{start}"

        response = requests.get(
            url, headers=headers, timeout=30
        )

        if response.status_code == 401 and not token:
            token = getpass.getpass(
                "Upstox access token: "
            )
            headers["Authorization"] = "Bearer " + token
            response = requests.get(
                url, headers=headers, timeout=30
            )

        if response.status_code != 200:
            raise SystemExit(
                f"Provider stopped: HTTP {response.status_code}"
            )

        payload = response.json()

        if payload.get("status") != "success":
            raise SystemExit("Provider rejected data request")

        candles = payload["data"]["candles"]
        rows.extend(candles)

        print("Downloaded batch:", batch + 1,
              "candles:", len(candles))

        end = start - timedelta(days=1)

    df = pd.DataFrame(rows, columns=[
        "timestamp", "Open", "High", "Low",
        "Close", "Volume", "OI"
    ])

# 2. Validate market candles

df["timestamp"] = pd.to_datetime(
    df.timestamp, utc=True
)

cols = ["Open", "High", "Low", "Close"]

df[cols] = df[cols].apply(
    pd.to_numeric, errors="raise"
)

if not np.isfinite(df[cols]).all().all():
    raise SystemExit("Invalid OHLC")

if (df[cols] <= 0).any().any():
    raise SystemExit("Invalid prices")

if (
    (df.High < df[cols].max(axis=1)).any()
    or (df.Low > df[cols].min(axis=1)).any()
):
    raise SystemExit("Invalid OHLC structure")

if (
    df.groupby("timestamp")[cols].nunique() > 1
).any().any():
    raise SystemExit("Conflicting candles")

df = df.drop_duplicates("timestamp")
df = df.sort_values("timestamp")

local = df.timestamp.dt.tz_convert(IST)
minutes = local.dt.hour * 60 + local.dt.minute

df = df[
    (minutes >= 555)
    & (minutes < 930)
    & (df.timestamp == df.timestamp.dt.floor("min"))
    & (
        df.timestamp + pd.Timedelta(minutes=1)
        <= pd.Timestamp.now(tz="UTC")
    )
].copy()

df = df.reset_index(drop=True)
df.to_csv(CACHE, index=False)

df["segment"] = (
    df.timestamp.diff() != pd.Timedelta(minutes=1)
).cumsum()

print("Validated candles:", len(df))

# 3. Causal feature engineering

def features(g):
    g = g.copy()
    c = g.Close

    for n in (1, 3, 5, 10, 15, 30):
        g[f"return_{n}"] = c.pct_change(n)

    for n in (9, 20, 50):
        ema = c.ewm(span=n, adjust=False).mean()
        g[f"ema_{n}"] = c / ema - 1

    delta = c.diff()

    gain = delta.clip(lower=0).ewm(
        alpha=1/14, adjust=False
    ).mean()

    loss = (-delta.clip(upper=0)).ewm(
        alpha=1/14, adjust=False
    ).mean()

    g["rsi"] = 100 - 100 / (
        1 + gain / loss.clip(lower=1e-10)
    )

    macd = (
        c.ewm(span=12, adjust=False).mean()
        - c.ewm(span=26, adjust=False).mean()
    )

    g["macd_hist"] = (
        macd - macd.ewm(span=9, adjust=False).mean()
    ) / c

    tr = pd.concat([
        g.High - g.Low,
        (g.High - c.shift()).abs(),
        (g.Low - c.shift()).abs()
    ], axis=1).max(axis=1)

    g["atr"] = tr.rolling(14).mean() / c

    g["volatility"] = (
        c.pct_change().rolling(20).std()
    )

    g["body"] = (c - g.Open) / c

    g["upper_wick"] = (
        g.High - g[["Open", "Close"]].max(axis=1)
    ) / c

    g["lower_wick"] = (
        g[["Open", "Close"]].min(axis=1) - g.Low
    ) / c

    g["resistance"] = (
        g.High.shift().rolling(20).max() / c - 1
    )

    g["support"] = (
        c / g.Low.shift().rolling(20).min() - 1
    )

    g["efficiency"] = (
        c.diff(20).abs()
        / c.diff().abs().rolling(20).sum()
    )

    for tf in (5, 15):
        a = g.set_index("timestamp")

        r = a.Close.resample(
            f"{tf}min",
            label="right",
            closed="left"
        )

        higher = r.last().loc[r.count() == tf]

        trend = (
            higher.ewm(span=3, adjust=False).mean()
            / higher.ewm(span=5, adjust=False).mean()
            - 1
        )

        available = pd.DatetimeIndex(
            g.timestamp + pd.Timedelta(minutes=1)
        )

        g[f"trend_{tf}m"] = trend.reindex(
            available, method="ffill"
        ).to_numpy()

    g["bullish_engulfing"] = (
        (c > g.Open)
        & (c.shift() < g.Open.shift())
        & (g.Open <= c.shift())
        & (c >= g.Open.shift())
    ).astype(int)

    g["bearish_engulfing"] = (
        (c < g.Open)
        & (c.shift() > g.Open.shift())
        & (g.Open >= c.shift())
        & (c <= g.Open.shift())
    ).astype(int)

    for h in (5, 10, 15):
        g[f"future_{h}"] = (
            c.shift(-h) / c - 1
        )

    return g

data = pd.concat([
    features(g)
    for _, g in df.groupby("segment", sort=True)
], ignore_index=True)

data = data.replace([np.inf, -np.inf], np.nan)

excluded = {
    "timestamp", "Open", "High", "Low",
    "Close", "Volume", "OI", "segment"
}

FEATURES = [
    c for c in data.columns
    if c not in excluded
    and not c.startswith("future_")
]

# 4. Independent model training

report = {}

for h in (5, 10, 15):

    print("\n===== HORIZON:", h, "MINUTES =====")

    target = f"future_{h}"

    d = data.dropna(
        subset=FEATURES + [target]
    ).reset_index(drop=True)

    if len(d) < 10000:
        print("Insufficient training data")
        continue

    X = d[FEATURES]
    y = (d[target] > 0).astype(int)

    a = int(len(d) * 0.60)
    b = int(len(d) * 0.80)

    train = slice(0, a - h)
    calibration = slice(a, b - h)
    test = slice(b, None)

    def make_models():
        return [
            XGBClassifier(
                n_estimators=150,
                max_depth=3,
                learning_rate=0.03,
                random_state=42,
                n_jobs=2,
                eval_metric="logloss"
            ),
            LGBMClassifier(
                n_estimators=150,
                max_depth=3,
                learning_rate=0.03,
                random_state=42,
                n_jobs=2,
                verbosity=-1
            )
        ]

    def probability(models, inputs):
        return np.mean([
            m.predict_proba(inputs)[:, 1]
            for m in models
        ], axis=0)

    # 5. Chronological walk-forward checks

    folds = TimeSeriesSplit(
        n_splits=3, gap=h
    )

    for tr, va in folds.split(X.iloc[train]):

        fold_models = make_models()

        for model in fold_models:
            model.fit(X.iloc[tr], y.iloc[tr])

        p = probability(fold_models, X.iloc[va])

        print(
            "Walk-forward accuracy:",
            round(accuracy_score(
                y.iloc[va], p >= 0.5
            ) * 100, 2)
        )

    models = make_models()

    for model in models:
        model.fit(X.iloc[train], y.iloc[train])

    # 6. Probability calibration

    raw_cal = probability(
        models, X.iloc[calibration]
    )

    calibrator = LogisticRegression()

    calibrator.fit(
        raw_cal.reshape(-1, 1),
        y.iloc[calibration]
    )

    raw_test = probability(
        models, X.iloc[test]
    )

    probs = calibrator.predict_proba(
        raw_test.reshape(-1, 1)
    )[:, 1]

    individual = np.array([
        model.predict_proba(X.iloc[test])[:, 1]
        for model in models
    ])

    # 7. Fixed confidence and agreement filter

    signals = np.where(
        (probs >= 0.65)
        & (individual.min(axis=0) > 0.5),
        1,
        np.where(
            (probs <= 0.35)
            & (individual.max(axis=0) < 0.5),
            -1, 0
        )
    )

    held = d.iloc[test].reset_index(drop=True)

    wins = losses = 0
    returns = []
    next_entry = None

    # Illustrative round-trip cost: 5 basis points.
    cost = 0.0005

    for i, signal in enumerate(signals):

        t = held.timestamp.iloc[i]

        if signal == 0:
            continue

        if next_entry is not None and t < next_entry:
            continue

        ret = signal * held[target].iloc[i] - cost

        returns.append(float(ret))

        wins += int(ret > 0)
        losses += int(ret <= 0)

        next_entry = t + pd.Timedelta(minutes=h)

    total = wins + losses

    result = {
        "holdout_rows": len(held),
        "direction_accuracy_pct": round(
            100 * accuracy_score(
                y.iloc[test], probs >= 0.5
            ), 2
        ),
        "brier_score": float(
            brier_score_loss(y.iloc[test], probs)
        ),
        "filtered_predictions": total,
        "positive_net_returns": wins,
        "nonpositive_net_returns": losses,
        "cost_adjusted_win_rate_pct": (
            round(100 * wins / total, 2)
            if total else None
        ),
        "mean_net_return_pct": (
            float(np.mean(returns) * 100)
            if returns else None
        ),
        "status": "RESEARCH_ONLY"
    }

    report[str(h)] = result

    joblib.dump({
        "models": models,
        "calibrator": calibrator,
        "features": FEATURES,
        "horizon": h,
        "execution_enabled": False,
        "status": "RESEARCH_ONLY"
    }, MODELS / f"nifty_{h}m.joblib")

    print(json.dumps(result, indent=2))

# 8. Final report

(ROOT / "ml_report.json").write_text(
    json.dumps(report, indent=2)
)

print("\n===== FINAL ML REPORT =====")
print(json.dumps(report, indent=2))
print("BROKER ORDERS: 0")
print("EXECUTION ENABLED: False")
print("REAL-MONEY READY: False")
print("REPORT:", ROOT / "ml_report.json")
