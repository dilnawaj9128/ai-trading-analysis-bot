import asyncio
import json

from websockets.asyncio.server import serve

from market_data.providers.connection_manager import ConnectionManager
from market_data.providers.candle_builder import CandleBuilder
from market_data.providers.candle_repository import CandleRepository
from market_data.providers.gap_detector import CandleGapDetector


def test_websocket_to_sqlite_pipeline(tmp_path):
    async def run():
        repo = CandleRepository(tmp_path / "pipeline.db")
        builder = CandleBuilder()
        gaps = CandleGapDetector()
        missing_counts = []

        ticks = [
            ("2026-11-22T10:00:00Z", 1.1000),
            ("2026-11-22T10:00:30Z", 1.1020),
            ("2026-11-22T10:01:00Z", 1.1010),
            ("2026-11-22T10:01:30Z", 1.1030),
            ("2026-11-22T10:04:00Z", 1.1040),
        ]

        async def handler(websocket):
            for timestamp, price in ticks:
                await websocket.send(json.dumps({
                    "timestamp": timestamp,
                    "price": price,
                }))

        async def on_message(message):
            candle = builder.add_tick(
                message["timestamp"],
                message["price"],
            )

            if candle is not None:
                missing = gaps.check(candle["timestamp"])
                missing_counts.append(missing)

                repo.save_candle(
                    candle,
                    symbol="EURUSD_otc",
                    source="SIMULATED",
                )

        async with serve(
            handler, "127.0.0.1", 0
        ) as server:
            port = server.sockets[0].getsockname()[1]

            manager = ConnectionManager(
                f"ws://127.0.0.1:{port}",
                max_retries=1,
                base_delay=0.001,
            )

            await manager.run(on_message)

        assert repo.count_candles() == 2
        assert missing_counts == [0, 0]

        with repo._connect() as conn:
            rows = conn.execute("""
                SELECT timestamp, open, high, low, close
                FROM candles
                ORDER BY timestamp
            """).fetchall()

        assert rows[0][1:] == (
            1.1000, 1.1020, 1.1000, 1.1020
        )

        assert rows[1][1:] == (
            1.1010, 1.1030, 1.1010, 1.1030
        )

        assert builder.current["open"] == 1.1040

    asyncio.run(run())
