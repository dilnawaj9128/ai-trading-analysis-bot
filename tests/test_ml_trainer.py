import numpy as np
import pandas as pd
import pytest
from analysis.ml_trainer import evaluate_models


def sample(n=400):
    rng = np.random.default_rng(42)
    t = pd.date_range('2026-01-05', periods=n, freq='min', tz='UTC')
    d = {'timestamp': t, 'outcome_timestamp': t + pd.Timedelta(minutes=15),
         'label_up_15m': np.array([0, 1] * ((n + 1) // 2))[:n]}
    for name in ('EMA_9', 'EMA_21', 'RSI_14', 'return_1m', 'return_5m',
                 'range_pct', 'ema_gap_pct', 'volatility_10', 'MACD', 'ATR_14'):
        d[name] = rng.normal(size=n)
    return pd.DataFrame(d)


def test_evaluation_has_baseline_and_models():
    result = evaluate_models(sample())
    assert len(result['scores']) == 4
    assert result['purged_rows'] >= 15
    assert result['train_rows'] + result['test_rows'] + result['purged_rows'] == 400
    assert result['scores']['brier_score'].between(0, 1).all()


def test_single_class_rejected():
    data = sample()
    data['label_up_15m'] = 1
    with pytest.raises(ValueError, match='Both classes'):
        evaluate_models(data)


def test_future_timestamp_mismatch_rejected():
    data = sample()
    data.loc[0, 'outcome_timestamp'] += pd.Timedelta(minutes=1)
    with pytest.raises(ValueError, match='15-minute'):
        evaluate_models(data)


def test_duplicate_timestamps_rejected():
    data = sample()
    data.loc[1, 'timestamp'] = data.loc[0, 'timestamp']
    with pytest.raises(ValueError, match='unique'):
        evaluate_models(data)
