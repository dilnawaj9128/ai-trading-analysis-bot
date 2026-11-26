from pathlib import Path
import pandas as pd
import numpy as np
from lightgbm import LGBMClassifier

base = Path("data/research/nifty50")

def load(name):
    df = pd.read_csv(base / f"{name}.csv")
    df.columns = df.columns.str.lower()
    df["timestamp"] = pd.to_datetime(df.timestamp, utc=True)
    return df.sort_values("timestamp").drop_duplicates("timestamp").set_index("timestamp")

nifty = load("historical")
price = nifty["close"]
X = pd.DataFrame(index=nifty.index)

for name in ["historical", "bank", "vix", "etf"]:
    df = load(name)
    c = df["close"]

    for n in [1, 3, 5, 10, 15, 30, 60]:
        X[f"{name}_return_{n}"] = c.pct_change(n, fill_method=None)

    for n in [10, 20, 50]:
        X[f"{name}_ema_{n}"] = c / c.ewm(span=n, adjust=False).mean() - 1
        X[f"{name}_volatility_{n}"] = c.pct_change().rolling(n).std()

X["range"] = (nifty.high - nifty.low) / price
X["body"] = (price - nifty.open) / nifty.open

local = X.index.tz_convert("Asia/Kolkata")
X["minute"] = local.hour * 60 + local.minute
X = X.replace([np.inf, -np.inf], np.nan)

out = base / "walkforward_results"
out.mkdir(parents=True, exist_ok=True)

print("===== NIFTY WALK-FORWARD ENGINE =====")
print("Historical candles:", len(nifty))
print("Features:", len(X.columns))

for h in [5, 10, 15]:
    expiry = X.index + pd.Timedelta(minutes=h)
    future = pd.Series(price.reindex(expiry).values, index=X.index)

    valid = (
        X.notna().all(axis=1)
        & future.notna()
        & future.ne(price)
        & (local.date == expiry.tz_convert("Asia/Kolkata").date)
    )

    x = X.loc[valid]
    y = (future.loc[valid] > price.loc[valid]).astype(int)
    results = []

    for start in range(len(x)//2, len(x), 5000):
        test = x.iloc[start:start+5000]
        cutoff = test.index[0] - pd.Timedelta(minutes=h)
        train = x.loc[x.index < cutoff]
        target = y.loc[train.index]

        model = LGBMClassifier(
            n_estimators=250,
            learning_rate=0.025,
            num_leaves=15,
            min_child_samples=100,
            reg_lambda=5,
            verbosity=-1,
            random_state=42,
            n_jobs=4
        )

        model.fit(train, target)
        p = model.predict_proba(test)[:, 1]
        actual = y.loc[test.index].values

        result = pd.DataFrame({
            "timestamp": test.index,
            "expiry": test.index + pd.Timedelta(minutes=h),
            "entry_price": price.loc[test.index].values,
            "expiry_price": future.loc[test.index].values,
            "up_score": p,
            "down_score": 1-p,
            "prediction": np.where(p >= 0.5, "UP", "DOWN"),
            "actual": np.where(actual == 1, "UP", "DOWN"),
            "correct": (p >= 0.5) == actual,
            "baseline_correct": actual == int(target.mean() >= 0.5)
        })

        results.append(result)

    r = pd.concat(results, ignore_index=True)
    r.to_csv(out / f"{h}m_verified.csv", index=False)

    print(f"\n===== {h} MINUTE =====")
    print("Verified predictions:", len(r))
    print("Correct:", int(r.correct.sum()))
    print("Incorrect:", int((~r.correct).sum()))
    print("Accuracy:", round(r.correct.mean()*100, 2), "%")
    print("Baseline:", round(r.baseline_correct.mean()*100, 2), "%")

    confidence = r[["up_score", "down_score"]].max(axis=1)

    for threshold in [0.55, 0.60, 0.65, 0.70]:
        selected = r[confidence >= threshold]
        if len(selected):
            print(
                f"Threshold {threshold}:",
                "Samples:", len(selected),
                "Accuracy:", round(selected.correct.mean()*100, 2), "%"
            )

print("\nHISTORICAL VERIFICATION COMPLETE")
print("BROKER ORDERS: 0")
print("LIVE ACCURACY: NOT VERIFIED")
