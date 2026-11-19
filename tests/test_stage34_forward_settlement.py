"""Stage 34 checks are synthetic and never contact a provider."""
from datetime import datetime, timedelta, timezone
import pandas as pd
import pytest

from research.stage34_forward_settlement import settle_observation, summarize_outcomes

T = datetime(2026, 11, 19, 12, 0, tzinfo=timezone.utc)

def observation(signal="UP", entry=1.1000):
    return {"status": "VALID", "signal": signal, "analysis_only": True,
            "execution_enabled": False, "expiry_minutes": 15, "timeframe": "1min",
            "signal_time_utc": T.isoformat(),
            "observed_at_utc": T.isoformat(), "entry_reference_close": entry}

def future(exit_price=1.1010):
    start = T + timedelta(minutes=1)
    dates = pd.date_range(start, periods=14, freq="min", tz="UTC")
    closes = [1.1001] * 13 + [exit_price]
    return pd.DataFrame({"timestamp": dates,
                         "Open": [1.1000] * 14,
                         "High": [max(1.1012, exit_price)] * 14,
                         "Low": [min(1.0990, exit_price)] * 14,
                         "Close": closes})

def settle(obs=None, frame=None, **kwargs):
    return settle_observation(
        observation() if obs is None else obs,
        future() if frame is None else frame,
        received_at=kwargs.pop("received_at", T + timedelta(minutes=16)),
        simulated=kwargs.pop("simulated", True), **kwargs)

def test_up_win_at_exact_expiry():
    r = settle()
    assert (r["status"], r["result"], r["pnl_units"]) == ("SETTLED", "WIN", 0.8)
    assert r["mode"] == "SIMULATED"

def test_down_win_and_up_loss():
    assert settle(observation("DOWN"), future(1.0990))["result"] == "WIN"
    result = settle(observation("UP"), future(1.0990))
    assert (result["result"], result["pnl_units"]) == ("LOSS", -1.0)

def test_push_refunds():
    result = settle(frame=future(1.1000))
    assert (result["result"], result["pnl_units"]) == ("PUSH", 0.0)

def test_not_expired_yet():
    result = settle(received_at=T + timedelta(minutes=14))
    assert result["status"] == "PENDING"

def test_unverified_future_is_not_settled():
    result = settle(simulated=False)
    assert result["status"] == "PENDING"
    assert result["result"] is None

def test_stage33_blocked_observation_never_settles():
    obs = observation()
    obs.update(status="BLOCKED", signal="NO TRADE")
    assert settle(obs)["status"] == "PENDING"

def test_missing_expiry_candle_stays_pending():
    assert settle(frame=future().iloc[:-1])["status"] == "PENDING"

def test_duplicate_future_timestamps_rejected():
    df = future()
    df.loc[5, "timestamp"] = df.loc[4, "timestamp"]
    assert settle(frame=df)["status"] == "PENDING"

def test_future_arrived_before_original_signal_rejected():
    assert settle(received_at=T - timedelta(minutes=1))["status"] == "PENDING"

def test_backward_or_naive_timestamp_rejected():
    obs = observation()
    obs["signal_time_utc"] = "2026-11-19T12:00:00"
    assert settle(obs)["status"] == "PENDING"

def test_invalid_future_ohlc_rejected():
    df = future()
    df.loc[13, "High"] = 0.9
    assert settle(frame=df)["status"] == "PENDING"

def test_report_does_not_count_pending_as_win():
    results = [settle(), settle(observation("DOWN")), settle(frame=future(1.1)),
               settle(received_at=T + timedelta(minutes=1))]
    s = summarize_outcomes(results)
    assert (s["wins"], s["losses"], s["pushes"], s["pending"]) == (1, 1, 1, 1)
    assert s["win_rate"] == 0.5
    assert s["net_units"] == -0.2

def test_reject_invalid_payout():
    with pytest.raises(ValueError):
        settle(payout=1.2)
