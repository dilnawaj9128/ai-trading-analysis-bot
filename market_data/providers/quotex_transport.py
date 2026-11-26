import asyncio
import json
import logging

from websockets.asyncio.client import connect

logger = logging.getLogger(__name__)


class QuotexTransport:
    """
    Generic WebSocket transport for an authorized
    market-data endpoint.

    Does not implement Quotex authentication,
    undocumented protocol messages, or trading.
    """

    def __init__(self, url: str):
        if not url.startswith(("wss://", "ws://")):
            raise ValueError("Invalid WebSocket URL")

        self.url = url

    async def stream(self, on_message):
        async with connect(
            self.url,
            open_timeout=15,
            ping_interval=20,
            ping_timeout=20,
            max_size=1_000_000,
        ) as websocket:

            logger.info("WebSocket connected")

            async for message in websocket:
                try:
                    payload = json.loads(message)
                except (ValueError, TypeError):
                    logger.warning("Non-JSON message received")
                    continue

                await on_message(payload)
