"""Research-only expanding-window walk-forward evaluation."""

import numpy as np
import pandas as pd

from sklearn.dummy import DummyClassifier
from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, balanced_accuracy_score, brier_score_loss
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from analysis.ml_trainer import FEATURES


def evaluate_walk_forward(dataset, *, min_train=500, test_size=200, max_folds=10):
    if not isinstance(dataset, pd.DataFrame):
        raise ValueError("Expected DataFrame")

    if any(type(v) is not int for v in (min_train, test_size, max_folds)):
        raise ValueError("Window settings must be integers")

    if min_train < 100 or test_size < 30 or max_folds < 1:
        raise ValueError("Invalid window settings")

    required = set(FEATURES) | {
        "timestamp", "outcome_timestamp", "label_up_15m"
    }
    if not required.issubset(dataset.columns):
        raise ValueError(f"Missing columns: {sorted(required - set(dataset.columns))}")

    data = dataset.copy().reset_index(drop=True)
    data["timestamp"] = pd.to_datetime(data["timestamp"], utc=True)
    data["outcome_timestamp"] = pd.to_datetime(data["outcome_timestamp"], utc=True)

    if data[["timestamp", "outcome_timestamp"]].isna().any().any():
        raise ValueError("Invalid timestamps")

    if data["timestamp"].duplicated().any():
        raise ValueError("Duplicate timestamps")

    if not data["timestamp"].is_monotonic_increasing:
        raise ValueError("Timestamps must be sorted")

    if not (
        data["outcome_timestamp"] - data["timestamp"]
    ).eq(pd.Timedelta(minutes=15)).all():
        raise ValueError("Expected exact 15-minute outcomes")

    y = data["label_up_15m"]
    if y.isna().any() or not y.isin([0, 1]).all():
        raise ValueError("Invalid labels")

    x = data.loc[:, FEATURES].apply(pd.to_numeric, errors="raise")
    if not np.isfinite(x.to_numpy(dtype=float)).all():
        raise ValueError("Invalid feature values")

    if len(data) < min_train + test_size + 16:
        raise ValueError("Insufficient training data")

    models = {
        "Majority baseline": lambda: DummyClassifier(strategy="prior"),
        "Logistic Regression": lambda: make_pipeline(
            StandardScaler(),
            LogisticRegression(max_iter=1000, random_state=42),
        ),
        "Random Forest": lambda: RandomForestClassifier(
            n_estimators=150,
            max_depth=6,
            min_samples_leaf=10,
            random_state=42,
            n_jobs=1,
        ),
        "Gradient Boosting": lambda: GradientBoostingClassifier(
            n_estimators=100,
            max_depth=2,
            learning_rate=0.05,
            random_state=42,
        ),
    }

    results = []
    fold = 0

    for cut in range(min_train + 16, len(data) - test_size + 1, test_size):
        if fold >= max_folds:
            break

        first_test = data["timestamp"].iloc[cut]

        train_idx = np.flatnonzero(
            (
                (data.index < cut)
                & (data["outcome_timestamp"] < first_test)
            ).to_numpy()
        )
        test_idx = np.arange(cut, cut + test_size)

        if len(train_idx) < min_train:
            continue

        if y.iloc[train_idx].nunique() < 2:
            continue

        fold += 1

        for name, factory in models.items():
            model = factory()
            model.fit(x.iloc[train_idx], y.iloc[train_idx].astype(int))

            up_index = list(model.classes_).index(1)
            probabilities = model.predict_proba(x.iloc[test_idx])[:, up_index]
            predictions = (probabilities >= 0.5).astype(int)
            actual = y.iloc[test_idx].astype(int)

            results.append({
                "fold": fold,
                "model": name,
                "train_rows": len(train_idx),
                "test_rows": len(test_idx),
                "test_start": first_test.isoformat(),
                "accuracy": float(accuracy_score(actual, predictions)),
                "balanced_accuracy": float(
                    balanced_accuracy_score(actual, predictions)
                ),
                "brier_score": float(
                    brier_score_loss(actual, probabilities)
                ),
            })

    if not results:
        raise ValueError("No valid folds")

    details = pd.DataFrame(results)

    summary = (
        details.groupby("model", as_index=False)
        .agg(
            folds=("fold", "nunique"),
            mean_accuracy=("accuracy", "mean"),
            mean_balanced_accuracy=("balanced_accuracy", "mean"),
            mean_brier=("brier_score", "mean"),
        )
        .sort_values("mean_brier")
        .reset_index(drop=True)
    )

    return {
        "summary": summary,
        "folds": details,
        "analysis_only": True,
        "execution_enabled": False,
    }
