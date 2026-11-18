"""Offline tests; no API keys or external requests."""
import pytest
from dashboard.signal_readiness import assess_signal_readiness


def assess(**overrides):
    kwargs = dict(expiry_minutes=15, stale=False, gaps=0,
                  fetch_status="SUCCESS", completed_candles=100,
                  provider_feed_verified=False, broker_feed_verified=False,
                  feed_mode="unknown", quality_status="UNKNOWN")
    kwargs.update(overrides)
    return assess_signal_readiness(**kwargs)


def test_unverified_feed_fail_closed():
    result = assess()
    assert result["signal"] == "NO TRADE"
    assert any("provenance" in x for x in result["reasons"])
    assert result["execution_enabled"] is False


def test_stale_gaps_cached_are_blocked():
    result = assess(stale=True, gaps=2, fetch_status="WAITING")
    assert result["signal"] == "NO TRADE"
    assert any("cached" in x for x in result["reasons"])
    assert any("gaps" in x for x in result["reasons"])


def test_unknown_quality_and_mode_are_blocked():
    result = assess(provider_feed_verified=True, broker_feed_verified=True)
    assert result["signal"] == "NO TRADE"
    assert any("feed mode" in x for x in result["reasons"])
    assert any("quality" in x for x in result["reasons"])


def test_even_verified_preliminary_gates_do_not_generate_direction():
    result = assess(provider_feed_verified=True, broker_feed_verified=True,
                    feed_mode="live", quality_status="VALID")
    assert result["signal"] == "NO TRADE"
    assert any("separate review" in x for x in result["reasons"])


@pytest.mark.parametrize("expiry", [1, 5, 15])
def test_supported_expiries(expiry):
    assert assess(expiry_minutes=expiry)["expiry_minutes"] == expiry


@pytest.mark.parametrize("expiry", [0, 2, 30, None, True])
def test_invalid_expiry_rejected(expiry):
    with pytest.raises(ValueError):
        assess(expiry_minutes=expiry)
