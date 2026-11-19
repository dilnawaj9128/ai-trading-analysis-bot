"""Stage 52A: unprotected legacy HTTP routes must fail closed."""

from datetime import datetime, timedelta, timezone

import pytest

from data.providers.forex_provider import TwelveDataProvider
from data import twelve_data_historical as historical


def test_legacy_forex_transport_blocked():
    provider = object.__new__(TwelveDataProvider)

    class NoNetwork:
        def get(self, *args, **kwargs):
            raise AssertionError("HTTP must not execute")

    provider.session = NoNetwork()

    with pytest.raises(
        RuntimeError, match="STAGE52_LEGACY_HTTP_BLOCKED"
    ):
        provider.get_candles(
            "EUR/USD", "1min", 120
        )


def test_default_historical_transport_blocked(monkeypatch):
    def no_network(*args, **kwargs):
        raise AssertionError("HTTP must not execute")

    monkeypatch.setattr(historical, "urlopen", no_network)

    with pytest.raises(
        RuntimeError, match="STAGE52_LEGACY_HTTP_BLOCKED"
    ):
        historical._default_fetch(
            {"symbol": "EUR/USD"}, "TEST_KEY"
        )


def test_historical_download_without_fetcher_blocked(tmp_path):
    start = datetime(
        2026, 11, 12, 10, 0, tzinfo=timezone.utc
    )

    with pytest.raises(
        RuntimeError, match="STAGE52_LEGACY_HTTP_BLOCKED"
    ):
        historical.download_eurusd(
            start=start,
            end=start + timedelta(minutes=30),
            output_dir=tmp_path / "download",
            api_key="TEST_KEY",
            fetcher=None,
        )

    assert not (tmp_path / "download").exists()
