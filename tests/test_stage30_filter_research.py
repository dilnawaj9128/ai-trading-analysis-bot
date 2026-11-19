"""Selection-policy unit tests: no profitable holdout inference is assumed."""
from scripts.run_stage30_filter_research import choose_candidate, conservative_signal


def summary(resolved, net, win_rate, breakeven=1 / 1.8):
    return {"resolved": resolved, "net_units": net, "win_rate": win_rate,
            "breakeven_win_rate": breakeven}


def test_rejects_negative_results():
    candidates = {
        "baseline": summary(38, -3.8, 0.5),
        "trend": summary(31, -1.4, 0.516),
    }
    assert choose_candidate(candidates) is None


def test_rejects_small_sample_even_if_profitable():
    assert choose_candidate({"rsi": summary(9, 6, 0.9)}) is None


def test_rejects_below_breakeven():
    assert choose_candidate({"rsi": summary(40, 1, 0.50)}) is None


def test_selects_training_candidate_without_holdout_input():
    candidates = {
        "baseline": summary(40, 1, 0.6),
        "trend": summary(40, 2, 0.65),
    }
    assert choose_candidate(candidates) == "trend"


def test_existing_signal_is_not_rewritten_if_no_trade(monkeypatch):
    monkeypatch.setattr(
        "scripts.run_stage30_filter_research.existing_strategy_on_prefix",
        lambda _: "NO TRADE",
    )
    assert conservative_signal(None, variant="trend_rsi") == "NO TRADE"
