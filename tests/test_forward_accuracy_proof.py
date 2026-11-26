import numpy as np
from simulator.forward_accuracy_proof import ForwardAccuracyProver


def _make_candles(n: int = 90):
    rng = np.random.default_rng(101)
    price = 25500.0
    out = []
    for i in range(n):
        step = rng.normal(1.2, 6.0)
        o = price
        c = round(o + step, 2)
        h = round(max(o, c) + 3.0, 2)
        l = round(min(o, c) - 3.0, 2)
        out.append({"timestamp": f"2026-11-26T09:{i % 60:02d}:00Z", "open": o, "high": h, "low": l, "close": c, "volume": 1000})
        price = c
    return out


def test_forward_accuracy_proof_generates_report(tmp_path):
    prover = ForwardAccuracyProver(
        db_path=str(tmp_path / "fwd.db"),
        model_dir=str(tmp_path / "models"),
        min_confidence=0.50,
        warmup_bars=45,
    )
    rep = prover.run_forward_proof(
        symbol="NIFTY50",
        expiry_minutes=5,
        candles=_make_candles(85),
        horizon_bars=1,
        report_path=str(tmp_path / "proof.json"),
    )
    assert rep["bars_evaluated"] > 0
    assert 0.0 <= rep["accuracy_win_rate"] <= 1.0
    assert (tmp_path / "proof.json").exists()
