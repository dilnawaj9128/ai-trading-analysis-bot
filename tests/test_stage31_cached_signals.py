"""Stage 31 research safeguards and parity tests."""
import pandas as pd
import pytest

from research.stage31_cached_signals import CachedSignalResearch, assert_prefix_parity
from scripts.run_stage31_cached_research import run


def sample(n=120):
    ts = pd.date_range("2026-11-16 09:00", periods=n, freq="min", tz="UTC")
    close = [1.10 + 0.00001 * i + 0.0001 * (i % 11) for i in range(n)]
    return pd.DataFrame({
        "timestamp": ts,
        "Open": close,
        "High": [v + 0.0002 for v in close],
        "Low": [v - 0.0002 for v in close],
        "Close": close,
    })


def test_parity_causal_cache_matches_existing_implementation():
    candles = sample()
    assert_prefix_parity(candles, CachedSignalResearch(candles), indices=(59, 61, 80, 100))


def test_rejects_different_dataset_at_matching_length():
    candles = sample()
    cache = CachedSignalResearch(candles)
    other = candles.iloc[:80].copy()
    other.loc[79, "Close"] += 0.00001
    with pytest.raises(ValueError, match="Prefix does not match"):
        cache.signal(other)


def test_rejects_unsupported_variant():
    cache = CachedSignalResearch(sample())
    with pytest.raises(ValueError, match="Unsupported candidate"):
        cache.for_variant("random")


def test_rejects_unsorted_timestamps():
    candles = sample()
    candles.loc[70, "timestamp"] = candles.loc[69, "timestamp"]
    with pytest.raises(ValueError):
        CachedSignalResearch(candles)


def test_small_sample_cannot_claim_profitable_selected_strategy():
    result = run(sample(), check_parity=False)
    assert result["selected"] is None
    assert result["holdout"] is None
    assert "NO TRADE" in result["decision"]
