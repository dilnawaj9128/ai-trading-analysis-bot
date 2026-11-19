"""Retired legacy Forex transport.

Direct provider requests are disabled until this client is migrated
to the central authorization and credit management system.
"""

import pandas as pd

from data.providers.base import MarketDataProvider


class TwelveDataProvider(MarketDataProvider):
    def __init__(self):
        # Preserve the legacy class interface without creating HTTP sessions.
        self.session = None

    def get_candles(
        self,
        symbol: str,
        interval: str,
        outputsize: int = 500,
    ) -> pd.DataFrame:
        raise RuntimeError(
            "STAGE52_LEGACY_HTTP_BLOCKED: "
            "Unprotected Forex provider requests are disabled"
        )
