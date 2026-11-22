import asyncio
from datetime import datetime, timezone, timedelta

import pytest

from market_data.providers.connection_manager import ConnectionManager
from market_data.providers.gap_detector import CandleGapDetector


def test_gap_detection():
    detector = CandleGapDetector()
    start = datetime(2026, 11, 22, 10, 0, tzinfo=timezone.utc)

    assert detector.check(start) == 0
    assert detector.check(start + timedelta(minutes=1)) == 0
    assert detector.check(start + timedelta(minutes=4)) == 2


def test_duplicate_rejection():
    detector = CandleGapDetector()
    timestamp = datetime(2026, 11, 22, 10, 0, tzinfo=timezone.utc)

    detector.check(timestamp)

    with pytest.raises(ValueError):
        detector.check(timestamp)


def test_reconnect_after_failure():
    attempts = []

    class FakeTransport:
        def __init__(self, url):
            self.url = url

        async def stream(self, callback):
            attempts.append(1)
            if len(attempts) == 1:
                raise ConnectionError("Simulated disconnect")
            await callback({"price": 1.1000})

    async def run():
        received = []

        async def callback(message):
            received.append(message)

        manager = ConnectionManager(
            "ws://localhost:1234",
            max_retries=2,
            base_delay=0.001,
            transport_factory=FakeTransport,
        )

        await manager.run(callback)

        assert len(attempts) == 2
        assert received == [{"price": 1.1000}]

    asyncio.run(run())


def test_retry_limit():
    class FailingTransport:
        def __init__(self, url):
            pass

        async def stream(self, callback):
            raise ConnectionError("Offline")

    async def run():
        manager = ConnectionManager(
            "ws://localhost:1234",
            max_retries=1,
            base_delay=0.001,
            transport_factory=FailingTransport,
        )

        with pytest.raises(ConnectionError):
            await manager.run(lambda message: None)

    asyncio.run(run())
