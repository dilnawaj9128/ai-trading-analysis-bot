import os
import json
import time
from pathlib import Path
from urllib.parse import quote

import numpy as np
import pandas as pd
import requests
import joblib

from xgboost import XGBClassifier
from lightgbm import LGBMClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import TimeSeriesSplit
from sklearn.metrics import (
    accuracy_score, brier_score_loss
)

ROOT = Path("data/research/nifty50")
MODELS = Path("models/nifty50/enhanced")
MODELS.mkdir(parents=True, exist_ok=True)

BASE = "https://api.upstox.com/v3/historical-candle"

headers = {"Accept": "application/json"}

token = os.getenv("UPSTOX_ACCESS_TOKEN")

if token:
    headers["Authorization"] = "Bearer " + token

COLS = [
    "timestamp", "Open", "High", "Low",
    "Close", "Volume", "OI"
]

REQUESTS = 0

print("===== ENHANCED NIFTY ML ENGINE =====")


def validate(df):
    df = df[COLS].copy()

    df.timestamp = pd.to_datetime(
        df.timestamp, utc=True, errors="raise"
    )

    prices = ["Open", "High", "Low", "Close"]

    for col in COLS[1:]:
        df[col] = pd.to_numeric(
            df[col], errors="raise"
        )

    if not np.isfinite(df[COLS[1:]]).all().all():
        raise ValueError("Invalid numeric data")

    if (
        (df[prices] <= 0).any().any()
        or (df.High < df[prices].max(axis=1)).any()
        or (df.Low > df[prices].min(axis=1)).any()
        or (df.Volume < 0).any()
    ):
        raise ValueError("Invalid OHLCV")

    if (
        df.groupby("timestamp")[COLS[1:]]
        .nunique().gt(1).any().any()
    ):
        raise ValueError("Conflicting duplicate data")

    local = df.timestamp.dt.tz_convert("Asia/Kolkata")

    minute = local.dt.hour * 60 + local.dt.minute

    df = df[
        (minute >= 555)
        & (minute < 930)
        & (df.timestamp == df.timestamp.dt.floor("min"))
        & (
            df.timestamp + pd.Timedelta(minutes=1)
            <= pd.Timestamp.now(tz="UTC")
        )
    ]

    return (
        df.drop_duplicates("timestamp")
        .sort_values("timestamp")
        .reset_index(drop=True)
    )


nifty = validate(pd.read_csv(ROOT / "historical.csv"))

start = nifty.timestamp.min().tz_convert(
    "Asia/Kolkata"
).date()

end = nifty.timestamp.max().tz_convert(
    "Asia/Kolkata"
).date()

print("Existing Nifty candles:", len(nifty))


def download(name, key):
    global REQUESTS

    cache = ROOT / f"{name}.csv"

    if cache.exists():
        return validate(pd.read_csv(cache))

    rows = []
    cursor = start

    while cursor <= end:
        finish = min(
            end,
            cursor + pd.Timedelta(days=27)
        )

        url = (
            f"{BASE}/{quote(key, safe='')}"
            f"/minutes/1/{finish}/{cursor}"
        )

        REQUESTS += 1

        response = requests.get(
            url, headers=headers, timeout=30
        )

        if response.status_code != 200:
            raise RuntimeError(
                f"{name}: HTTP {response.status_code}"
            )

        payload = response.json()

        if payload.get("status") != "success":
            raise RuntimeError(
                f"{name}: provider rejected request"
            )

        chunk = payload["data"]["candles"]

        rows.extend(chunk)

        print(name, cursor, finish, len(chunk))

        cursor = finish + pd.Timedelta(days=1)

        time.sleep(0.4)

    result = validate(pd.DataFrame(rows, columns=COLS))

    if result.empty:
        raise RuntimeError(f"{name}: no candles")

    result.to_csv(cache, index=False)

    return result


# Additional market context

sources = {
    "bank": "NSE_INDEX|Nifty Bank",
    "vix": "NSE_INDEX|India VIX",
    "etf": "NSE_EQ|INF204KB14I2"
}

market = nifty.copy()

available = []
unavailable = {}

for name, key in sources.items():
    try:
        extra = download(name, key)

        extra = extra.rename(columns={
            c: f"{name}_{c}" for c in COLS[1:]
        })

        market = market.merge(
            extra,
            on="timestamp",
            how="left",
            validate="one_to_one"
        )

        available.append(name)

    except Exception as exc:
        unavailable[name] = type(exc).__name__
        print("SOURCE UNAVAILABLE:", name, str(exc))

print("Available sources:", available)
print("Unavailable sources:", unavailable)

if not available:
    raise SystemExit(
        "STOP: No additional market data available"
    )

market = market.sort_values("timestamp")

market["segment"] = (
    market.timestamp.diff()
    != pd.Timedelta(minutes=1)
).cumsum()


# Causal feature engineering

def build(g):
    g = g.copy()

    c = g.Close

    for n in (1, 3, 5, 10, 15, 30, 60):
        g[f"ret_{n}"] = c.pct_change(
            n, fill_method=None
        )

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

    g["macd"] = (
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

    g["efficiency"] = (
        c.diff(20).abs()
        / c.diff().abs().rolling(20).sum()
    )

    g["resistance"] = (
        g.High.shift().rolling(20).max() / c - 1
    )

    g["support"] = (
        c / g.Low.shift().rolling(20).min() - 1
    )

    # Market session

    local = g.timestamp.dt.tz_convert(
        "Asia/Kolkata"
    )

    g["session_minute"] = (
        local.dt.hour * 60 + local.dt.minute - 555
    ) / 375

    g["opening_range_position"] = (
        c / g.Open.iloc[0] - 1
    )

    # Completed higher-timeframe candles

    for tf in (5, 15):
        r = g.set_index("timestamp").Close.resample(
            f"{tf}min",
            label="right",
            closed="left",
            origin="start_day",
            offset="15min"
        )

        higher = r.last().loc[r.count() == tf]

        trend = (
            higher.ewm(span=3, adjust=False).mean()
            / higher.ewm(span=5, adjust=False).mean()
            - 1
        )

        g[f"trend_{tf}m"] = trend.reindex(
            pd.DatetimeIndex(
                g.timestamp + pd.Timedelta(minutes=1)
            ),
            method="ffill"
        ).to_numpy()

    # Cross-market momentum and correlation

    for name in available:
        ext = g[f"{name}_Close"]

        for n in (1, 5, 15):
            g[f"{name}_ret_{n}"] = ext.pct_change(
                n, fill_method=None
            )

        ext_ret = ext.pct_change(fill_method=None)

        g[f"{name}_correlation"] = (
            c.pct_change().rolling(30).corr(ext_ret)
        )

        g[f"{name}_relative_strength"] = (
            ext.pct_change(15, fill_method=None)
            - c.pct_change(15, fill_method=None)
        )

    # ETF volume and VWAP

    if "etf" in available:
        volume = g.etf_Volume

        typical = (
            g.etf_High + g.etf_Low + g.etf_Close
        ) / 3

        vwap = (
            (typical * volume).cumsum()
            / volume.cumsum().replace(0, np.nan)
        )

        g["etf_vwap_distance"] = (
            g.etf_Close / vwap - 1
        )

        g["etf_relative_volume"] = (
            volume
            / volume.rolling(20).mean()
              .replace(0, np.nan)
        )

    if "bank" in available and "etf" in available:
        g["market_agreement"] = (
            np.sign(g.bank_ret_5)
            + np.sign(g.etf_ret_5)
            + np.sign(g.ret_5)
        ) / 3

    # Next-candle entry; no same-close execution.
    # Exit at nominal horizon boundary.

    for h in (5, 10, 15):
        g[f"future_{h}"] = (
            g.Open.shift(-(h + 1))
            / g.Open.shift(-1) - 1
        )

    return g


data = pd.concat([
    build(g)
    for _, g in market.groupby("segment")
    if len(g) >= 80
], ignore_index=True)

data = data.replace([np.inf, -np.inf], np.nan)

raw = set(COLS + ["segment"])

for name in available:
    raw.update(f"{name}_{c}" for c in COLS[1:])

features = [
    c for c in data.columns
    if c not in raw
    and not c.startswith("future_")
]

print("ML features:", len(features))


# Model training

def new_models():
    return [
        XGBClassifier(
            n_estimators=200,
            max_depth=3,
            learning_rate=0.025,
            subsample=0.8,
            colsample_bytree=0.8,
            n_jobs=2,
            random_state=42,
            eval_metric="logloss"
        ),
        LGBMClassifier(
            n_estimators=200,
            max_depth=4,
            num_leaves=15,
            learning_rate=0.025,
            n_jobs=2,
            random_state=42,
            verbosity=-1
        )
    ]


def fit_models(X, y):
    models = new_models()

    for model in models:
        model.fit(X, y)

    return models


def probability(models, X):
    return np.mean([
        m.predict_proba(X)[:, 1]
        for m in models
    ], axis=0)


def score(d, p, h, threshold, cost):
    wins = losses = 0
    returns = []
    next_entry = None

    for i, prob in enumerate(p):

        signal = (
            1 if prob >= threshold
            else -1 if prob <= 1-threshold
            else 0
        )

        if not signal:
            continue

        t = d.timestamp.iloc[i]

        if next_entry is not None and t < next_entry:
            continue

        ret = signal * d[f"future_{h}"].iloc[i] - cost

        returns.append(float(ret))

        wins += int(ret > 0)
        losses += int(ret <= 0)

        next_entry = t + pd.Timedelta(minutes=h)

    return {
        "predictions": wins + losses,
        "wins": wins,
        "losses": losses,
        "net_return_pct": float(sum(returns)*100),
        "mean_return_pct": (
            float(np.mean(returns)*100)
            if returns else None
        ),
        "win_rate_pct": (
            100*wins/(wins+losses)
            if wins+losses else None
        )
    }


report = {}

for h in (5, 10, 15):

    print("\n===== HORIZON", h, "MINUTES =====")

    target = f"future_{h}"

    d = data.dropna(
        subset=features+[target]
    ).sort_values("timestamp").reset_index(drop=True)

    print("Usable samples:", len(d))

    if len(d) < 10000:
        print("INSUFFICIENT ALIGNED DATA")
        continue

    X = d[features]

    # Volatility-adjusted training labels.
    # Neutral movements excluded from fitting only.

    margin = np.maximum(
        0.0005,
        d.atr * 0.5
    )

    meaningful = d[target].abs() > margin

    y = (d[target] > 0).astype(int)

    a = int(len(d)*0.55)
    b = int(len(d)*0.70)
    c = int(len(d)*0.85)

    gap = h + 1

    train = np.arange(0, a-gap)
    cal = np.arange(a, b-gap)
    tune = np.arange(b, c-gap)
    test = np.arange(c, len(d))

    folds = TimeSeriesSplit(
        n_splits=3, gap=gap
    )

    for tr, va in folds.split(train):
        idx = train[tr]
        idx = idx[meaningful.iloc[idx].to_numpy()]

        fold_models = fit_models(
            X.iloc[idx], y.iloc[idx]
        )

        p = probability(fold_models, X.iloc[train[va]])

        print(
            "Walk-forward accuracy:",
            round(
                accuracy_score(
                    y.iloc[train[va]], p >= 0.5
                ) * 100, 2
            )
        )

    idx = train[meaningful.iloc[train].to_numpy()]

    models = fit_models(X.iloc[idx], y.iloc[idx])

    calibrator = LogisticRegression()

    raw_cal = probability(models, X.iloc[cal])

    calibrator.fit(
        raw_cal.reshape(-1, 1),
        y.iloc[cal]
    )

    def calibrated(indices):
        p = probability(models, X.iloc[indices])

        return calibrator.predict_proba(
            p.reshape(-1, 1)
        )[:, 1]

    # Select threshold on tuning data ONLY.

    tune_p = calibrated(tune)
    tune_data = d.iloc[tune].reset_index(drop=True)

    eligible = []

    for threshold in (0.53, 0.55, 0.58, 0.60, 0.65):

        performance = score(
            tune_data, tune_p, h, threshold, 0.0005
        )

        if (
            performance["predictions"] >= 100
            and performance["net_return_pct"] > 0
        ):
            eligible.append((
                threshold,
                performance["mean_return_pct"]
            ))

    selected = (
        max(eligible, key=lambda x: x[1])[0]
        if eligible else None
    )

    # Independent holdout; no threshold adjustment.

    p = calibrated(test)

    test_data = d.iloc[test].reset_index(drop=True)

    evaluation = {
        "horizon": h,
        "holdout_samples": len(test),
        "direction_accuracy_pct": float(
            accuracy_score(
                y.iloc[test], p >= 0.5
            ) * 100
        ),
        "majority_baseline_pct": float(
            max(y.iloc[test].mean(),
                1-y.iloc[test].mean())*100
        ),
        "brier_score": float(
            brier_score_loss(y.iloc[test], p)
        ),
        "selected_threshold": selected,
        "cost_scenarios": {},
        "status": "RESEARCH_ONLY"
    }

    if selected is not None:
        for cost in (0.0003, 0.0005, 0.001):
            evaluation["cost_scenarios"][str(cost)] = (
                score(test_data, p, h, selected, cost)
            )

    else:
        evaluation["reason"] = (
            "No profitable threshold on tuning data"
        )

    report[str(h)] = evaluation

    joblib.dump({
        "models": models,
        "calibrator": calibrator,
        "features": features,
        "threshold": selected,
        "required_sources": available,
        "horizon": h,
        "status": "RESEARCH_ONLY",
        "execution_enabled": False
    }, MODELS / f"nifty_enhanced_{h}m.joblib")

    print(json.dumps(evaluation, indent=2))


final = {
    "nifty_candles": len(nifty),
    "available_sources": available,
    "unavailable_sources": unavailable,
    "feature_count": len(features),
    "results": report,
    "new_http_requests": REQUESTS,
    "broker_orders": 0,
    "execution_enabled": False,
    "real_money_ready": False
}

path = ROOT / "enhanced_ml_report.json"

path.write_text(json.dumps(final, indent=2))

print("\n===== FINAL ENHANCED ML REPORT =====")
print(json.dumps(final, indent=2))
print("REPORT SAVED:", path)
print("RESEARCH DEPLOYMENT COMPLETE")
