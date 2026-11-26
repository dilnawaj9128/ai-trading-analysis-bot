from strategy.session_filter import MarketSessionFilter
from strategy.regime_risk_filter import DecisionRiskEngine


def test_indian_session_blocks_open_spike_and_allows_midday():
    # 09:20 IST -> 03:50 UTC (blocked opening noise)
    ok_open, _ = MarketSessionFilter.check_session("BANKNIFTY", "2026-11-26T03:50:00Z")
    assert ok_open is False

    # 11:30 IST -> 06:00 UTC (allowed prime session)
    ok_mid, _ = MarketSessionFilter.check_session("BANKNIFTY", "2026-11-26T06:00:00Z")
    assert ok_mid is True


def test_fx_session_allows_london_and_blocks_asian_dead_zone():
    # 14:30 IST -> 09:00 UTC (London session - allowed)
    ok_lon, _ = MarketSessionFilter.check_session("QX:EURUSD", "2026-11-26T09:00:00Z")
    assert ok_lon is True

    # 04:30 IST -> 23:00 UTC prev day (low liquidity - blocked)
    ok_off, _ = MarketSessionFilter.check_session("QX:EURUSD", "2026-11-25T23:00:00Z")
    assert ok_off is False


def test_risk_engine_enforces_session_filter():
    engine = DecisionRiskEngine(min_confidence=0.60)
    res = engine.evaluate(
        symbol="NIFTY50",
        expiry_minutes=5,
        ml_output={"prob_up": 0.80, "prob_down": 0.20},
        latest_features={"atr_pct": 0.0012, "ema_diff": 0.0008, "macd_hist": 0.0003, "rsi_norm": 0.2},
        timestamp_str="2026-11-26T03:50:00Z",  # 09:20 IST
        enforce_session=True,
    )
    assert res["signal"] == "NO TRADE"
    assert "09:45-15:10 IST" in res["reasons"][0]
