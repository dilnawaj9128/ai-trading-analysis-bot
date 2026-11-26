import numpy as np
from simulator.live_paper_ledger import PaperTradingLedger
from simulator.drift_retrainer import DriftAutoRetrainer


def _candles(n: int = 65):
    rng = np.random.default_rng(77)
    p = 52000.0
    rows = []
    for i in range(n):
        o = p
        c = round(o + rng.normal(2.0, 12.0), 2)
        rows.append({"timestamp": f"2026-11-26T10:{i % 60:02d}:00Z", "open": o, "high": max(o, c) + 5.0, "low": min(o, c) - 5.0, "close": c, "volume": 100})
        p = c
    return rows


def test_drift_retrainer_triggers_on_low_win_rate(tmp_path):
    ledger = PaperTradingLedger(db_path=str(tmp_path / "drift.db"))
    for _ in range(12):
        tid = ledger.record_signal("BANKNIFTY", 5, "UP", 0.70, 52000.0, stake=100.0)
        ledger.settle_trade(tid, exit_price=51950.0)  # all losses -> drift_detected=True

    retrainer = DriftAutoRetrainer(ledger=ledger, model_dir=str(tmp_path / "models"), min_candles_to_retrain=40)
    out = retrainer.check_and_retrain(_candles(60), horizon_bars=1)
    assert out["retrained"] is True
