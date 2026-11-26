import asyncio
import json

from datetime import datetime, timezone
from websockets.asyncio.server import serve

from market_data.providers.quotex_transport import QuotexTransport
from market_data.providers.candle_builder import CandleBuilder


def test_candle_builder():
    builder = CandleBuilder()

    assert builder.add_tick(
        datetime(2026, 11, 22, 10, 0, 0, tzinfo=timezone.utc),
        1.1000,
    ) is None

    builder.add_tick(
        datetime(2026, 11, 22, 10, 0, 30, tzinfo=timezone.utc),
        1.1010,
    )

    completed = builder.add_tick(
        datetime(2026, 11, 22, 10, 1, 0, tzinfo=timezone.utc),
        1.1005,
    )

    assert completed["open"] == 1.1000
    assert completed["high"] == 1.1010
    assert completed["low"] == 1.1000
    assert completed["close"] == 1.1010


def test_local_websocket_stream():
    async def run():
        received = []

        async def handler(websocket):
            await websocket.send(json.dumps({
                "timestamp": "2026-11-22T10:00:00Z",
                "price": 1.1000,
            }))
            await websocket.send(json.dumps({
                "timestamp": "2026-11-22T10:01:00Z",
                "price": 1.1005,
            }))

        async def on_message(message):
            received.append(message)

        async with serve(handler, "127.0.0.1", 0) as server:
            port = server.sockets[0].getsockname()[1]
            transport = QuotexTransport(
                f"ws://127.0.0.1:{port}"
            )
            await transport.stream(on_message)

        assert len(received) == 2
        assert received[0]["price"] == 1.1000
        assert received[1]["price"] == 1.1005

    asyncio.run(run())
