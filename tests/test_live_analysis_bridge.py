"""Offline one-fetch-to-analysis safety and integration tests."""
from datetime import datetime, timedelta, timezone
import pandas as pd
import pytest

from market_data.live_analysis_bridge import analyze_fetched_candles

NOW = datetime(2026, 11, 20, 6, 30, tzinfo=timezone.utc)


def fetched(n=120):
    stamps = [NOW - timedelta(minutes=n - i) for i in range(n)]
    frame = pd.DataFrame({"timestamp": stamps, "Open": [1.1]*n,
                          "High": [1.11]*n, "Low": [1.09]*n, "Close": [1.105]*n})
    return {"frame": frame, "symbol": "EUR/USD", "interval": "1min", "candles": n,
            "analysis_only": True, "execution_enabled": False}


def engines():
    def indicator(frame):
        frame = frame.copy()
        frame["RSI_14"] = 50.
        return {"frame": frame}
    def market(result, **kwargs):
        return {"condition": "sideways", "explanation": "Flat"}
    def signal(frame, **kwargs):
        return {"signal": "NO TRADE", "expiry_minutes": 15, "reasons": ["Unknown feed"]}
    return {"indicator_engine": indicator, "market_engine": market, "signal_engine": signal}


def test_same_fetch_yields_indicator_report_without_http():
    r = fetched()
    out = analyze_fetched_candles(r, now=NOW, **engines())
    assert out["signal"] == "NO TRADE"
    assert out["indicators"]["RSI_14"] == 50
    assert out["extra_http_requests"] == out["broker_orders"] == 0
    assert out["candles"] == 120 and out["expiry_minutes"] == 15
    assert "RSI_14" not in r["frame"]


def test_stale_fetched_candles_are_only_research():
    out = analyze_fetched_candles(fetched(), now=NOW + timedelta(hours=1), **engines())
    assert out["stale"] and out["signal"] == "NO TRADE"


def test_rejects_direction_from_unknown_provider_feed():
    es = engines()
    es["signal_engine"] = lambda *_args, **_kw: {"signal": "UP", "expiry_minutes": 15}
    with pytest.raises(ValueError, match="NO TRADE"):
        analyze_fetched_candles(fetched(), now=NOW, **es)


@pytest.mark.parametrize("tamper", [
    lambda r: r.update(execution_enabled=True),
    lambda r: r.update(candles=119),
    lambda r: r.update(symbol="GBP/USD"),
    lambda r: r["frame"].__setitem__("timestamp", [NOW]*120),
    lambda r: r["frame"].__setitem__("High", [1.0]*120),
    lambda r: r["frame"].__setitem__("Close", [-1.0]*120),
])
def test_rejects_invalid_or_unsafe_input(tamper):
    r = fetched()
    tamper(r)
    with pytest.raises((ValueError, TypeError)):
        analyze_fetched_candles(r, now=NOW, **engines())


def test_missing_data_rejected():
    with pytest.raises(ValueError, match="60"):
        analyze_fetched_candles(fetched(50), now=NOW, **engines())


def test_future_clock_rejected():
    with pytest.raises(ValueError, match="Future"):
        analyze_fetched_candles(fetched(), now=NOW - timedelta(hours=1), **engines())


def test_one_fetch_reuses_exact_frame_for_analysis(monkeypatch):
    from scripts import run_one_normal_fetch as app
    from market_data import live_analysis_bridge as bridge
    calls = {"fetch": 0, "analysis": 0}
    frame = fetched()["frame"]
    monkeypatch.setattr(app, "load_credit_state", lambda: object())
    monkeypatch.setattr(app, "create_research_config", lambda *a: object())
    def only_fetch(*args, **kwargs):
        calls["fetch"] += 1
        return {"frame": frame, "candles": 120, "analysis_only": True}
    monkeypatch.setattr(app, "fetch_authorized_live_candles", only_fetch)
    def only_analyze(value):
        calls["analysis"] += 1
        assert value["frame"] is frame
        return {"signal": "NO TRADE", "extra_http_requests": 0}
    monkeypatch.setattr(bridge, "analyze_fetched_candles", only_analyze)
    result = app.fetch_one_research_snapshot(approved=True, api_key="fake", include_analysis=True)
    assert calls == {"fetch": 1, "analysis": 1}
    assert result["analysis"]["signal"] == "NO TRADE"


def test_preview_does_not_fetch(monkeypatch, capsys):
    from scripts import run_one_normal_fetch as app
    monkeypatch.setattr("sys.argv", ["run_one_normal_fetch", "--analyze"])
    monkeypatch.setattr(app, "fetch_one_research_snapshot", lambda **kwargs: (_ for _ in ()).throw(AssertionError("fetch called")))
    app.main()
    assert "PREVIEW ONLY" in capsys.readouterr().out
