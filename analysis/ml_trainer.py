"""Research-only chronological evaluation of 15-minute candle outcomes."""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.dummy import DummyClassifier
from sklearn.ensemble import GradientBoostingClassifier, RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, balanced_accuracy_score, brier_score_loss
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

FEATURES = ('EMA_9', 'EMA_21', 'RSI_14', 'return_1m', 'return_5m',
            'range_pct', 'ema_gap_pct', 'volatility_10', 'MACD', 'ATR_14')


def evaluate_models(dataset: pd.DataFrame, *, test_fraction: float = 0.2, min_train: int = 100):
    """Evaluate one chronological holdout with a purged 15-minute label boundary.

    This is a baseline holdout, not full walk-forward evaluation. Never use
    the holdout to claim production accuracy or repeatedly tune the model.
    """
    if not isinstance(dataset, pd.DataFrame):
        raise ValueError('Expected DataFrame')
    required = set(FEATURES) | {'timestamp', 'outcome_timestamp', 'label_up_15m'}
    if not required.issubset(dataset.columns):
        raise ValueError(f'Missing columns: {sorted(required - set(dataset.columns))}')
    if not 0.1 <= test_fraction <= 0.4:
        raise ValueError('test_fraction must be 0.1 to 0.4')
    if type(min_train) is not int or min_train < 20:
        raise ValueError('min_train must be >= 20')
    data = dataset.copy()
    data['timestamp'] = pd.to_datetime(data['timestamp'], utc=True, errors='raise')
    data['outcome_timestamp'] = pd.to_datetime(data['outcome_timestamp'], utc=True, errors='raise')
    if data[['timestamp', 'outcome_timestamp']].isna().any().any():
        raise ValueError('Invalid timestamps')
    if data['timestamp'].duplicated().any() or not data['timestamp'].is_monotonic_increasing:
        raise ValueError('Timestamps must be unique and chronologically sorted')
    if not (data['outcome_timestamp'] - data['timestamp']).eq(pd.Timedelta(minutes=15)).all():
        raise ValueError('Expected exact 15-minute outcomes')
    y = data['label_up_15m']
    if y.isna().any() or not y.isin([0, 1]).all():
        raise ValueError('Labels must be binary')
    x = data.loc[:, FEATURES].apply(pd.to_numeric, errors='raise')
    if not np.isfinite(x.to_numpy(dtype=float)).all():
        raise ValueError('Non-finite feature values')
    if len(data) < min_train + 20:
        raise ValueError('Insufficient rows for chronological evaluation')
    cut = int(len(data) * (1 - test_fraction))
    first_test_time = data['timestamp'].iloc[cut]
    train_mask = (data.index < cut) & (data['outcome_timestamp'] < first_test_time)
    train_idx = np.flatnonzero(train_mask.to_numpy())
    test_idx = np.arange(cut, len(data))
    if len(train_idx) < min_train or len(test_idx) < 20:
        raise ValueError('Insufficient rows after purging')
    if y.iloc[train_idx].nunique() < 2 or y.iloc[test_idx].nunique() < 2:
        raise ValueError('Both classes required in train and test; collect varied historical data')
    models = {
        'Majority baseline': DummyClassifier(strategy='prior'),
        'Logistic Regression': make_pipeline(StandardScaler(), LogisticRegression(max_iter=1000, random_state=42)),
        'Random Forest': RandomForestClassifier(n_estimators=150, max_depth=6, min_samples_leaf=10, random_state=42, n_jobs=1),
        'Gradient Boosting': GradientBoostingClassifier(n_estimators=100, max_depth=2, learning_rate=0.05, random_state=42),
    }
    scores = []
    for name, model in models.items():
        model.fit(x.iloc[train_idx], y.iloc[train_idx].astype(int))
        prob = model.predict_proba(x.iloc[test_idx])[:, list(model.classes_).index(1)]
        predicted = (prob >= 0.5).astype(int)
        scores.append({'model': name,
                       'accuracy': float(accuracy_score(y.iloc[test_idx], predicted)),
                       'balanced_accuracy': float(balanced_accuracy_score(y.iloc[test_idx], predicted)),
                       'brier_score': float(brier_score_loss(y.iloc[test_idx], prob))})
    return {'scores': pd.DataFrame(scores).sort_values('brier_score').reset_index(drop=True),
            'train_rows': len(train_idx), 'test_rows': len(test_idx),
            'purged_rows': cut - len(train_idx),
            'test_start': first_test_time.isoformat(),
            'analysis_only': True, 'execution_enabled': False}
