import pytest
from datetime import datetime, timezone
from data.providers.indian_indices_provider import IndianIndicesProvider
from data.providers.quotex_adapter import QuotexDataAdapter
from data.providers.multi_market_router import MultiMarketRouter


def test_indian_market_hours():
    # Thursday 10:30 AM IST -> 05:00 AM UTC
    open_dt = datetime(2026, 11, 26, 5, 0, tzinfo=timezone.utc)
    # Thursday 06:00 PM IST -> 12:30 PM UTC
    closed_dt = datetime(2026, 11, 26, 12, 30, tzinfo=timezone.utc)
    assert IndianIndicesProvider.is_market_open(open_dt) is True
    assert IndianIndicesProvider.is_market_open(closed_dt) is False


def test_quotex_adapter_blocks_otc_and_maps_fx():
    adapter = QuotexDataAdapter(allow_otc=False)
    assert adapter.resolve_symbol("EURUSD") == "EUR/USD"
    with pytest.raises(ValueError):
        adapter.resolve_symbol("EUR/USD (OTC)")


def test_multi_market_router():
    router = MultiMarketRouter()
    assert router.get_market_type("NIFTY50") == "INDIAN_INDICES"
    assert router.get_market_type("BANKNIFTY") == "INDIAN_INDICES"
    assert router.get_market_type("QX:EURUSD") == "QUOTEX"
    assert router.prepare_quotex_symbol("QX:GBPUSD") == "GBP/USD"
