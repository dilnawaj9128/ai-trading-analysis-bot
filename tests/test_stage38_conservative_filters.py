import pandas as pd
import pytest

from research import stage38_conservative_filters as mod


def row(atr=0.001, ema20=1.1001, ema50=1.1000):
    return {
        "Close": 1.1,
        "ATR_14": atr,
        "EMA_20": ema20,
        "EMA_50": ema50,
    }


def test_weak_trend_allowed():
    assert mod.passes_regime_filter(
        "UP", row(), "rsi_weak_trend"
    ) == "UP"


def test_strong_trend_rejected():
    assert mod.passes_regime_filter(
        "UP",
        row(ema20=1.102, ema50=1.100),
        "rsi_weak_trend",
    ) == "NO TRADE"


def test_low_volatility_allowed():
    assert mod.passes_regime_filter(
        "DOWN",
        row(atr=0.0001),
        "rsi_low_volatility",
    ) == "DOWN"


def test_high_volatility_rejected():
    assert mod.passes_regime_filter(
        "DOWN",
        row(atr=0.001),
        "rsi_low_volatility",
    ) == "NO TRADE"


def test_invalid_indicator_blocked():
    r = row()
    r["ATR_14"] = float("nan")

    assert mod.passes_regime_filter(
        "UP", r, "rsi_weak_trend"
    ) == "NO TRADE"


def test_no_trade_remains_no_trade():
    assert mod.passes_regime_filter(
        "NO TRADE", row(), "rsi_weak_trend"
    ) == "NO TRADE"


def test_unknown_variant_rejected():
    with pytest.raises(ValueError):
        mod.passes_regime_filter(
            "UP", row(), "unknown"
        )


def make_data(n=400):
    return pd.DataFrame({
        "timestamp": pd.date_range(
            "2026-11-01",
            periods=n,
            freq="min",
            tz="UTC",
        ),
        "Open": [1.1] * n,
        "High": [1.2] * n,
        "Low": [1.0] * n,
        "Close": [1.1] * n,
    })


def fake_research(monkeypatch, wins, losses):
    seen = []

    class FakeCache:
        def __init__(self, training):
            seen.append(("cache", len(training)))

        def signal(self, prefix, variant):
            return "UP"

    def fake_score(
        training, signal_fn, start, end, payout
    ):
        seen.append(("score", len(training), end))

        resolved = wins + losses

        return {
            "stats": {
                "wins": wins,
                "losses": losses,
                "pushes": 0,
                "resolved": resolved,
                "win_rate": wins / resolved if resolved else None,
                "net_units": round(
                    wins * payout - losses, 8
                ),
                "breakeven_win_rate": 1 / (1 + payout),
            },
            "trades": [],
        }

    monkeypatch.setattr(
        mod, "CachedSignalResearch", FakeCache
    )
    monkeypatch.setattr(
        mod, "score_window", fake_score
    )

    return seen


def test_future_data_excluded_from_training(monkeypatch):
    seen = fake_research(monkeypatch, 0, 0)

    result = mod.run_training_research(
        make_data(400),
        train_end=180,
    )

    assert result["training_candles"] == 180
    assert ("cache", 180) in seen

    for event in seen:
        if event[0] == "score":
            assert event[1:] == (180, 180)


def test_small_profitable_sample_not_selected(monkeypatch):
    fake_research(monkeypatch, 20, 10)

    result = mod.run_training_research(
        make_data(),
        train_end=180,
    )

    assert result["provisional"] is not None
    assert result["selected_for_future_research"] is None
    assert "insufficient" in result["decision"]


def test_confidence_filter_rejects_weak_edge(monkeypatch):
    fake_research(monkeypatch, 60, 40)

    result = mod.run_training_research(
        make_data(),
        train_end=180,
    )

    assert result["provisional"] is not None
    assert result["selected_for_future_research"] is None
    assert "confidence" in result["decision"]


def test_strong_synthetic_candidate_is_research_only(monkeypatch):
    fake_research(monkeypatch, 90, 10)

    result = mod.run_training_research(
        make_data(),
        train_end=180,
    )

    assert result["selected_for_future_research"] is not None
    assert result["independent_validation"] is False
    assert result["execution_enabled"] is False


def test_invalid_training_window():
    with pytest.raises(ValueError):
        mod.run_training_research(
            make_data(), train_end=500
        )


def test_invalid_payout():
    with pytest.raises(ValueError):
        mod.run_training_research(
            make_data(), payout=1.5
        )
