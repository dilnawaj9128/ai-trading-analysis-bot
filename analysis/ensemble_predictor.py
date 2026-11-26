from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional
import joblib
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import make_pipeline


class MultiModelEnsemble:
    """Soft-voting ensemble combining XGBoost, LightGBM, and Logistic Regression."""

    FEATURE_COLS = [
        "ret_1",
        "ret_3",
        "ret_5",
        "ema_diff",
        "rsi_norm",
        "macd_hist",
        "atr_pct",
        "body_ratio",
    ]

    def __init__(self, model_dir: str = "models/saved") -> None:
        self.model_dir = Path(model_dir)
        self.model_dir.mkdir(parents=True, exist_ok=True)
        self.models: Dict[str, Any] = {}
        self.is_trained: bool = False

    @classmethod
    def build_features(cls, candles: List[Dict[str, Any]]) -> pd.DataFrame:
        df = pd.DataFrame(candles).copy()
        for col in ("open", "high", "low", "close"):
            df[col] = df[col].astype(float)

        df["ret_1"] = df["close"].pct_change(1).fillna(0.0)
        df["ret_3"] = df["close"].pct_change(3).fillna(0.0)
        df["ret_5"] = df["close"].pct_change(5).fillna(0.0)

        ema_fast = df["close"].ewm(span=9, adjust=False).mean()
        ema_slow = df["close"].ewm(span=21, adjust=False).mean()
        df["ema_diff"] = ((ema_fast - ema_slow) / df["close"]).fillna(0.0)

        delta = df["close"].diff()
        gain = delta.clip(lower=0).rolling(14, min_periods=1).mean()
        loss = (-delta.clip(upper=0)).rolling(14, min_periods=1).mean()
        rs = gain / loss.replace(0, 1e-9)
        rsi = 100.0 - (100.0 / (1.0 + rs))
        df["rsi_norm"] = ((rsi - 50.0) / 50.0).fillna(0.0)

        ema12 = df["close"].ewm(span=12, adjust=False).mean()
        ema26 = df["close"].ewm(span=26, adjust=False).mean()
        macd = ema12 - ema26
        signal = macd.ewm(span=9, adjust=False).mean()
        df["macd_hist"] = ((macd - signal) / df["close"]).fillna(0.0)

        tr = np.maximum(
            df["high"] - df["low"],
            np.maximum(
                (df["high"] - df["close"].shift(1)).abs(),
                (df["low"] - df["close"].shift(1)).abs(),
            ),
        )
        atr = tr.rolling(14, min_periods=1).mean()
        df["atr_pct"] = (atr / df["close"]).fillna(0.0)

        candle_range = (df["high"] - df["low"]).replace(0, 1e-9)
        df["body_ratio"] = ((df["close"] - df["open"]) / candle_range).fillna(0.0)

        return df[cls.FEATURE_COLS].replace([np.inf, -np.inf], 0.0).fillna(0.0)

    def _init_estimators(self) -> Dict[str, Any]:
        estimators: Dict[str, Any] = {
            "logreg": make_pipeline(StandardScaler(), LogisticRegression(max_iter=500, random_state=42))
        }
        try:
            from xgboost import XGBClassifier
            estimators["xgb"] = XGBClassifier(
                n_estimators=80,
                max_depth=3,
                learning_rate=0.05,
                subsample=0.8,
                eval_metric="logloss",
                random_state=42,
            )
        except Exception:
            pass

        try:
            from lightgbm import LGBMClassifier
            estimators["lgbm"] = LGBMClassifier(
                n_estimators=80,
                max_depth=3,
                learning_rate=0.05,
                verbose=-1,
                random_state=42,
            )
        except Exception:
            pass

        return estimators

    def fit(self, candles: List[Dict[str, Any]], horizon_bars: int = 1) -> Dict[str, Any]:
        if len(candles) < 40:
            raise ValueError("Need at least 40 candles to train ensemble.")

        X = self.build_features(candles)
        closes = pd.Series([float(c["close"]) for c in candles])
        y = (closes.shift(-horizon_bars) > closes).astype(int)

        valid_mask = y.notna() & (X.index < len(candles) - horizon_bars)
        X_train = X.loc[valid_mask]
        y_train = y.loc[valid_mask]

        if y_train.nunique() < 2:
            raise ValueError("Target labels contain only one class; cannot train classifier.")

        self.models = self._init_estimators()
        for name, model in self.models.items():
            model.fit(X_train, y_train)

        self.is_trained = True
        return {"trained_models": list(self.models.keys()), "samples": int(len(X_train))}

    def predict_latest(self, candles: List[Dict[str, Any]]) -> Dict[str, Any]:
        if not self.is_trained or not self.models:
            raise RuntimeError("Ensemble model must be trained or loaded before prediction.")

        X = self.build_features(candles)
        latest_row = X.iloc[[-1]]

        per_model_up: Dict[str, float] = {}
        for name, model in self.models.items():
            prob_up = float(model.predict_proba(latest_row)[0][1])
            per_model_up[name] = round(prob_up, 4)

        avg_up = float(np.mean(list(per_model_up.values())))
        avg_down = 1.0 - avg_up

        return {
            "prob_up": round(avg_up, 4),
            "prob_down": round(avg_down, 4),
            "model_breakdown": per_model_up,
        }

    def save(self, tag: str = "default") -> Path:
        path = self.model_dir / f"ensemble_{tag}.joblib"
        joblib.dump({"models": self.models, "is_trained": self.is_trained}, path)
        return path

    def load(self, tag: str = "default") -> bool:
        path = self.model_dir / f"ensemble_{tag}.joblib"
        if not path.exists():
            return False
        payload = joblib.load(path)
        self.models = payload["models"]
        self.is_trained = payload["is_trained"]
        return True
