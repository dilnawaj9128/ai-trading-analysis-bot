import numpy as np
from analysis.unified_pipeline import UnifiedTradingPipeline


def _trending_candles(n: int = 80):
    rng = np.random.default_rng(7)
    price = 24000.0
    candles = []
    for i in range(n):
        drift = 4.0 if i > 50 else rng.normal(0.0, 5.0)
        open_p = price
        close_p = round(open_p + drift + rng.normal(0, 1.5), 2)
        high_p = round(max(open_p, close_p) + 2.0, 2)
        low_p = round(min(open_p, close_p) - 2.0, 2)
        candles.append(
            {
                "timestamp": f"2026-11-26T11:{i % 60:02d}:00Z",
                "open": open_p,
                "high": high_p,
                "low": low_p,
                "close": close_p,
                "volume": 5000,
            }
        )
        price = close_p
    return candles


def test_end_to_end_pipeline_and_paper_settlement(tmp_path):
    candles = _trending_candles(80)
    pipeline = UnifiedTradingPipeline(
        db_path=str(tmp_path / "paper.db"),
        model_dir=str(tmp_path / "models"),
    )
    result = pipeline.run_cycle(symbol="NIFTY50", expiry_minutes=5, candles=candles, model_tag="nifty_5m")
    assert result["signal"] in ("UP", "DOWN", "NO TRADE")
    assert "regime" in result

    # Verify manual trade entry + settlement + drift metrics
    tid = pipeline.ledger.record_signal("NIFTY50", 5, "UP", 0.71, entry_price=24100.0, stake=100.0)
    settled = pipeline.ledger.settle_trade(tid, exit_price=24125.0)
    assert settled["status"] == "WIN"
    assert settled["pnl"] == 80.0

    stats = pipeline.ledger.get_performance_and_drift()
    assert stats["wins"] == 1
    assert stats["balance"] == 10080.0
