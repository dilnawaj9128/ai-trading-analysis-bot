import asyncio
import logging

from market_data.providers.quotex_transport import QuotexTransport

logger = logging.getLogger(__name__)


class ConnectionManager:
    def __init__(
        self,
        url,
        max_retries=5,
        base_delay=1.0,
        max_delay=30.0,
        transport_factory=QuotexTransport,
    ):
        if max_retries < 0 or base_delay <= 0 or max_delay <= 0:
            raise ValueError("Invalid retry configuration")

        self.url = url
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.transport_factory = transport_factory

    async def run(self, on_message):
        failures = 0

        while True:
            try:
                transport = self.transport_factory(self.url)
                await transport.stream(on_message)

                # A completed stream is not necessarily an error.
                return

            except asyncio.CancelledError:
                raise

            except (OSError, TimeoutError, ConnectionError) as exc:
                failures += 1

                if failures > self.max_retries:
                    logger.error("Retry limit reached: %s", exc)
                    raise

                delay = min(
                    self.base_delay * (2 ** (failures - 1)),
                    self.max_delay,
                )

                logger.warning(
                    "Connection failed (%s/%s). Retry in %.1fs",
                    failures,
                    self.max_retries,
                    delay,
                )

                await asyncio.sleep(delay)
