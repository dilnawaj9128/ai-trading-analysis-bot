import json
import joblib
import numpy as np
import pandas as pd
from pathlib import Path
from lightgbm import LGBMClassifier
from xgboost import XGBClassifier
from sklearn.metrics import accuracy_score, brier_score_loss

ROOT = Path("data/research/nifty50")
OUT = Path("models/nifty50/candidate")
OUT.mkdir(parents=True, exist_ok=True)

d = pd.read_csv(ROOT / "historical.csv")
d.timestamp = pd.to_datetime(d.timestamp, utc=True)
d = d.sort_values("timestamp").drop_duplicates("timestamp")
d = d.set_index("timestamp")

p = d.Close
seg = (
    d.index.to_series().diff()
    != pd.Timedelta(minutes=1)
).cumsum()

X = pd.DataFrame(index=d.index)

for n in [1,3,5,10,15,30,60]:
    X[f"return_{n}"] = p.groupby(seg).pct_change(n)

for n in [10,20,50]:
    X[f"ema_{n}"] = p / p.groupby(seg).transform(
        lambda s: s.ewm(
            span=n, adjust=False, min_periods=n
        ).mean()
    ) - 1

    X[f"volatility_{n}"] = p.groupby(seg).transform(
        lambda s: s.pct_change().rolling(n).std()
    )

X["range"] = (d.High-d.Low)/p
X["body"] = (p-d.Open)/d.Open

local = d.index.tz_convert("Asia/Kolkata")
X["minute"] = local.hour*60 + local.minute
X = X.replace([np.inf,-np.inf],np.nan)

report = []

for h in [5,10,15]:
    future = p.groupby(seg).shift(-h)

    valid = (
        X.notna().all(axis=1)
        & future.notna()
        & future.ne(p)
    )

    x = X.loc[valid]
    y = (future.loc[valid] > p.loc[valid]).astype(int)

    a = int(len(x)*0.60)
    b = int(len(x)*0.80)

    tune = x.iloc[a:b]
    test = x.iloc[b:]

    train = x.loc[
        x.index < tune.index[0]-pd.Timedelta(minutes=h)
    ]

    tune = tune.loc[
        tune.index < test.index[0]-pd.Timedelta(minutes=h)
    ]

    models = {
        "LightGBM": LGBMClassifier(
            n_estimators=250,
            learning_rate=0.02,
            num_leaves=15,
            min_child_samples=100,
            reg_lambda=5,
            verbosity=-1,
            random_state=42,
            n_jobs=4
        ),
        "XGBoost": XGBClassifier(
            n_estimators=250,
            learning_rate=0.02,
            max_depth=3,
            min_child_weight=20,
            subsample=0.8,
            colsample_bytree=0.8,
            reg_lambda=5,
            random_state=42,
            n_jobs=4
        )
    }

    for model in models.values():
        model.fit(train,y.loc[train.index])

    probs = {
        name:model.predict_proba(tune)[:,1]
        for name,model in models.items()
    }

    probs["Ensemble"] = (
        probs["LightGBM"] + probs["XGBoost"]
    ) / 2

    selected = min(
        probs,
        key=lambda k: brier_score_loss(
            y.loc[tune.index],probs[k]
        )
    )

    q = probs[selected]
    threshold = None
    best = 0

    for t in [0.55,0.60,0.65,0.70,0.75]:
        mask = (q >= t) | (q <= 1-t)

        if mask.sum() < 100:
            continue

        acc = accuracy_score(
            y.loc[tune.index].to_numpy()[mask],
            (q[mask]>=0.5).astype(int)
        )

        if acc > best and acc > 0.56:
            best = acc
            threshold = t

    if selected == "Ensemble":
        qtest = sum(
            m.predict_proba(test)[:,1]
            for m in models.values()
        ) / 2
    else:
        qtest = models[selected].predict_proba(test)[:,1]

    acc = accuracy_score(
        y.loc[test.index],(qtest>=0.5).astype(int)
    )

    baseline = (
        y.loc[test.index] == int(y.loc[train.index].mean()>=0.5)
    ).mean()

    mask = (
        (qtest>=threshold)|(qtest<=1-threshold)
        if threshold is not None
        else np.zeros(len(test),dtype=bool)
    )

    filtered = (
        accuracy_score(
            y.loc[test.index].to_numpy()[mask],
            (qtest[mask]>=0.5).astype(int)
        )
        if mask.any() else None
    )

    result = {
        "timeframe":h,
        "selected_model":selected,
        "holdout_accuracy_pct":round(acc*100,2),
        "baseline_pct":round(baseline*100,2),
        "threshold":threshold,
        "filtered_predictions":int(mask.sum()),
        "filtered_accuracy_pct":(
            round(filtered*100,2)
            if filtered is not None else None
        ),
        "deployment_approved":False
    }

    report.append(result)

    joblib.dump(
        {
            "models":models,
            "selected":selected,
            "threshold":threshold,
            "features":list(X.columns)
        },
        OUT/f"candidate_{h}m.joblib"
    )

    print(json.dumps(result,indent=2),flush=True)

(OUT/"accuracy_report.json").write_text(
    json.dumps(report,indent=2)
)

print("ACCURACY EXPERIMENT COMPLETE")
print("EXISTING LIVE APPLICATION UNCHANGED")
print("AUTOMATIC MODEL REPLACEMENT: DISABLED")
print("BROKER ORDERS: 0")
