import numpy as np
from analysis.ensemble_predictor import MultiModelEnsemble
from strategy.regime_risk_filter import DecisionRiskEngine


def _make_sample_candles(n: int = 80):
    rng = np.random.default_rng(42)
    price = 1.1000
    candles = []
    for i in range(n):
        move = rng.normal(0.0001, 0.0008)
        open_p = price
        close_p = round(open_p + move, 5)
        high_p = round(max(open_p, close_p) + abs(rng.normal(0, 0.0003)), 5)
        low_p = round(min(open_p, close_p) - abs(rng.normal(0, 0.0003)), 5)
        candles.append(
            {
                "timestamp": f"2026-11-26T10:{i % 60:02d}:00Z",
                "open": open_p,
                "high": high_p,
                "low": low_p,
                "close": close_p,
                "volume": 1000,
            }
        )
        price = close_p
    return candles


def test_ensemble_fit_predict_and_persistence(tmp_path):
    candles = _make_sample_candles(80)
    ensemble = MultiModelEnsemble(model_dir=str(tmp_path))
    info = ensemble.fit(candles, horizon_bars=1)
    assert info["samples"] > 50
    assert "logreg" in info["trained_models"]

    pred = ensemble.predict_latest(candles)
    assert 0.0 <= pred["prob_up"] <= 1.0
    assert abs((pred["prob_up"] + pred["prob_down"]) - 1.0) < 1e-3

    ensemble.save("eurusd_5m")
    reloaded = MultiModelEnsemble(model_dir=str(tmp_path))
    assert reloaded.load("eurusd_5m") is True


def test_decision_engine_blocks_sideways_and_approves_aligned_trend():
    engine = DecisionRiskEngine(min_confidence=0.60)

    # Sideways market -> must return NO TRADE
    sideways_res = engine.evaluate(
        symbol="NIFTY50",
        expiry_minutes=5,
        ml_output={"prob_up": 0.72, "prob_down": 0.28},
        latest_features={"atr_pct": 0.00005, "ema_diff": 0.00002, "macd_hist": 0.0001, "rsi_norm": 0.1},
    )
    assert sideways_res["signal"] == "NO TRADE"

    # Strong aligned UP trend -> must return UP
    up_res = engine.evaluate(
        symbol="EUR/USD",
        expiry_minutes=5,
        ml_output={"prob_up": 0.68, "prob_down": 0.32},
        latest_features={"atr_pct": 0.0012, "ema_diff": 0.0008, "macd_hist": 0.0003, "rsi_norm": 0.2},
    )
    assert up_res["signal"] == "UP"
    assert len(up_res["reasons"]) > 0
