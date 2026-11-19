import pandas as pd
import pytest

from research.stage37_market_regime import (
    classify_regime,
    enrich_trades,
    group_performance,
    run_regime_analysis,
)


def row(ema20=1.102, ema50=1.100, atr=0.001):
    return {
        "Close": 1.1,
        "ATR_14": atr,
        "EMA_20": ema20,
        "EMA_50": ema50,
        "RSI_14": 60,
    }


def test_strong_trend():
    result = classify_regime(row())
    assert result["trend"] == "STRONG"


def test_weak_trend():
    result = classify_regime(
        row(ema20=1.1001, ema50=1.1000)
    )
    assert result["trend"] == "WEAK"


def test_high_volatility():
    result = classify_regime(row(atr=0.001))
    assert result["volatility"] == "HIGH"


def test_low_volatility():
    result = classify_regime(row(atr=0.0001))
    assert result["volatility"] == "LOW"


def test_invalid_indicator_returns_unknown():
    data = row()
    data["ATR_14"] = float("nan")

    result = classify_regime(data)
    assert result["trend"] == "UNKNOWN"


def test_rsi_zone():
    assert classify_regime(row())["rsi_zone"] == "BULLISH"


def test_group_win_loss_push():
    trades = [
        {"trend": "STRONG", "result": "WIN"},
        {"trend": "STRONG", "result": "LOSS"},
        {"trend": "STRONG", "result": "PUSH"},
    ]

    result = group_performance(trades, ("trend",))
    group = result[0]

    assert group["wins"] == 1
    assert group["losses"] == 1
    assert group["pushes"] == 1
    assert group["win_rate"] == 0.5
    assert group["net_units"] == -0.2


def test_no_trades_returns_empty():
    assert group_performance([], ("trend",)) == []


def test_reject_invalid_outcome():
    with pytest.raises(ValueError):
        group_performance(
            [{"trend": "STRONG", "result": "UNKNOWN"}],
            ("trend",),
        )


def test_indicators_never_see_future_candles():
    dates = pd.date_range(
        "2026-11-01",
        periods=100,
        freq="min",
        tz="UTC",
    )

    candles = pd.DataFrame({
        "timestamp": dates,
        "Open": [1.1] * 100,
        "High": [1.2] * 100,
        "Low": [1.0] * 100,
        "Close": [1.1] * 100,
    })

    trades = [{
        "signal_index": 65,
        "expiry_index": 80,
        "result": "WIN",
    }]

    lengths_seen = []

    def fake_indicators(prefix):
        lengths_seen.append(len(prefix))
        assert len(prefix) == 66

        result = prefix.copy()
        result["ATR_14"] = 0.001
        result["EMA_20"] = 1.102
        result["EMA_50"] = 1.100
        result["RSI_14"] = 60
        return result

    result = enrich_trades(
        candles,
        trades,
        indicator_fn=fake_indicators,
    )

    assert lengths_seen == [66]
    assert result[0]["trend"] == "STRONG"


def test_reject_wrong_signal_index():
    candles = pd.DataFrame({
        "Close": [1.1] * 10,
    })

    with pytest.raises(ValueError):
        enrich_trades(
            candles,
            [{
                "signal_index": 100,
                "expiry_index": 115,
                "result": "WIN",
            }],
        )


def test_full_regime_report_reconciles_totals():
    dates = pd.date_range(
        "2026-11-01",
        periods=100,
        freq="min",
        tz="UTC",
    )

    candles = pd.DataFrame({
        "timestamp": dates,
        "Open": [1.1] * 100,
        "High": [1.2] * 100,
        "Low": [1.0] * 100,
        "Close": [1.1] * 100,
    })

    def fake_walk_forward(candles, **kwargs):
        return {
            "test_trades": [{
                "signal_index": 65,
                "expiry_index": 80,
                "signal": "UP",
                "result": "WIN",
            }],
            "aggregate": {
                "resolved": 1,
                "net_units": 0.8,
            },
        }

    def fake_indicators(prefix):
        result = prefix.copy()
        result["ATR_14"] = 0.001
        result["EMA_20"] = 1.102
        result["EMA_50"] = 1.100
        result["RSI_14"] = 60
        return result

    report = run_regime_analysis(
        candles,
        walk_forward_fn=fake_walk_forward,
        indicator_fn=fake_indicators,
    )

    assert report["total_trades"] == 1
    assert report["by_trend"][0]["wins"] == 1
    assert report["execution_enabled"] is False
