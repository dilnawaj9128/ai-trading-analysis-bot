import pytest

from market_data.providers.quotex_transport import QuotexTransport


def test_valid_websocket_url():
    transport = QuotexTransport("wss://example.com/feed")
    assert transport.url == "wss://example.com/feed"


def test_invalid_websocket_url():
    with pytest.raises(ValueError):
        QuotexTransport("https://example.com/feed")


def test_stream_method_exists():
    transport = QuotexTransport("wss://example.com/feed")
    assert callable(transport.stream)
