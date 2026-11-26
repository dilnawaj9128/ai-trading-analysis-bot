from pathlib import Path
import json
import numpy as np
import pandas as pd
import joblib
from lightgbm import LGBMClassifier
from sklearn.metrics import roc_auc_score

ROOT = Path("data/research/nifty50")
OUT = Path("models/nifty50/final_research")
OUT.mkdir(parents=True, exist_ok=True)

def load(name):
    d = pd.read_csv(ROOT / f"{name}.csv")
    d.timestamp = pd.to_datetime(d.timestamp, utc=True)
    assert not d.timestamp.duplicated().any()
    return d.sort_values("timestamp")

d = load("historical")
for name in ["bank", "vix", "etf"]:
    x = load(name).set_index("timestamp").add_prefix(name+"_")
    d = d.join(x, on="timestamp", validate="one_to_one")

d = d.dropna().reset_index(drop=True)
d["segment"] = (
    d.timestamp.diff() != pd.Timedelta(minutes=1)
).cumsum()

def features(g):
    g = g.copy()
    c = g.Close
    for n in [1, 3, 5, 10, 15, 30, 60]:
        g[f"ret_{n}"] = c.pct_change(n)
    for n in [9, 20, 50]:
        g[f"ema_{n}"] = c/c.ewm(span=n).mean()-1
    g["volatility"] = c.pct_change().rolling(20).std()
    g["atr"] = (g.High-g.Low).rolling(14).mean()/c
    g["body"] = (c-g.Open)/c
    g["trend"] = c.pct_change(20)
    g["efficiency"] = (
        c.diff(20).abs() /
        c.diff().abs().rolling(20).sum()
    )
    g["session"] = (
        g.timestamp.dt.tz_convert("Asia/Kolkata")
        .dt.hour*60 +
        g.timestamp.dt.tz_convert("Asia/Kolkata")
        .dt.minute-555
    )/375

    for name in ["bank", "vix", "etf"]:
        x = g[f"{name}_Close"]
        for n in [1, 5, 15]:
            g[f"{name}_ret_{n}"] = x.pct_change(n)
        g[f"{name}_corr"] = (
            c.pct_change().rolling(30)
            .corr(x.pct_change())
        )

    v = g.etf_Volume
    typical = (
        g.etf_High+g.etf_Low+g.etf_Close
    )/3
    g["vwap"] = g.etf_Close / (
        (typical*v).cumsum()/v.cumsum()
    )-1
    g["relative_volume"] = v/v.rolling(20).mean()
    return g

raw = set(d.columns)
d = pd.concat([
    features(g) for _,g in d.groupby("segment")
    if len(g)>80
], ignore_index=True)

F = [c for c in d.columns if c not in raw]
d = d.replace([np.inf,-np.inf],np.nan)

def outcomes(g,h,side):
    op = g.Open.to_numpy()
    hi = g.High.to_numpy()
    lo = g.Low.to_numpy()
    cl = g.Close.to_numpy()
    atr = g.atr.to_numpy()
    result = np.full(len(g),np.nan)

    for i in range(len(g)-h):
        if not np.isfinite(atr[i]):
            continue
        entry = op[i+1]
        target = max(0.001,2*atr[i])
        stop = max(0.0007,atr[i])
        ret = side*(cl[i+h]/entry-1)

        for j in range(i+1,i+h+1):
            up = hi[j]/entry-1
            down = lo[j]/entry-1
            gain = up if side==1 else -down
            loss = -down if side==1 else up

            if loss>=stop:
                ret = -stop
                break
            if gain>=target:
                ret = target
                break

        result[i] = ret

    return pd.Series(result,index=g.index)

def model():
    return LGBMClassifier(
        n_estimators=180,
        max_depth=4,
        num_leaves=15,
        learning_rate=0.025,
        random_state=42,
        n_jobs=2,
        verbosity=-1
    )

report = {}
for h in [5,10,15]:
    for side in [1,-1]:
        key = f"{h}m_{'UP' if side==1 else 'DOWN'}"
        print("\nRESEARCH:",key,flush=True)

        r = pd.concat([
            outcomes(g,h,side)
            for _,g in d.groupby("segment")
        ])
        z = d.assign(outcome=r).dropna(
            subset=F+["outcome"]
        ).reset_index(drop=True)

        X = z[F]
        y = (z.outcome>0.0005).astype(int)
        n = len(z)
        a,b = int(n*.60),int(n*.80)
        gap = h+1

        m = model()
        m.fit(X.iloc[:a-gap],y.iloc[:a-gap])

        importance = pd.Series(
            m.feature_importances_,index=F
        ).sort_values(ascending=False)

        selected = importance.head(20).index.tolist()
        m = model()
        m.fit(
            X[selected].iloc[:a-gap],
            y.iloc[:a-gap]
        )

        def evaluate(start,end,threshold,cost):
            p = m.predict_proba(
                X[selected].iloc[start:end]
            )[:,1]
            returns = []
            next_time = None

            for i,prob in enumerate(p,start):
                t = z.timestamp.iloc[i]
                if prob<threshold:
                    continue
                if next_time is not None and t<next_time:
                    continue
                returns.append(z.outcome.iloc[i]-cost)
                next_time = t+pd.Timedelta(minutes=h+1)

            return {
                "trades":len(returns),
                "win_rate":float(np.mean(
                    np.array(returns)>0
                )*100) if returns else None,
                "net_return_pct":float(sum(returns)*100)
            }

        candidates = []
        for threshold in [.55,.60,.65,.70,.75]:
            s = evaluate(a,b-gap,threshold,.0005)
            if s["trades"]>=100 and s["net_return_pct"]>0:
                candidates.append((s["net_return_pct"],threshold))

        threshold = max(candidates)[1] if candidates else None

        result = {
            "threshold":threshold,
            "status":"NO_TRADE",
            "historical_research_only":True,
            "fresh_validation":False
        }

        if threshold is not None:
            result["historical_results"] = {
                str(cost):evaluate(b,n,threshold,cost)
                for cost in [.0003,.0005,.001]
            }

        joblib.dump({
            "model":m,
            "features":selected,
            "threshold":threshold,
            "execution_enabled":False
        },OUT/f"{key}.joblib")

        probability = float(
            m.predict_proba(X[selected].tail(1))[0, 1]
        )
        result["setup_direction"] = "UP" if side == 1 else "DOWN"
        result["setup_success_score_pct"] = round(probability * 100, 2)
        result["status"] = "RESEARCH_ONLY"
        result["trade_approved"] = False
        report[key] = result
        print(json.dumps(result,indent=2))

path = ROOT/"final_research_report.json"
path.write_text(json.dumps(report,indent=2))
print("\n===== FINAL RESEARCH REPORT =====")
print(json.dumps(report,indent=2))
print("API REQUESTS: 0")
print("BROKER ORDERS: 0")
print("REAL MONEY READY: FALSE")
print("REPORT:",path)
