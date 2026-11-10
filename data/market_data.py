
from datetime import datetime, timezone

import pandas as pd

from config import (
    DATA_MODE,
    DEFAULT_SYMBOL,
    DEFAULT_INTERVAL,
    OUTPUT_SIZE,
    SUPPORTED_INTERVALS
)

from data.providers.forex_provider import TwelveDataProvider
from data.data_validator import DataValidator


class MarketDataService:

    def __init__(self):
        self.provider = TwelveDataProvider()
        self.validator = DataValidator()

    def get_market_data(
        self,
        symbol=DEFAULT_SYMBOL,
        interval=DEFAULT_INTERVAL,
        outputsize=OUTPUT_SIZE
    ):

        if interval not in SUPPORTED_INTERVALS:
            raise ValueError(
                f"Unsupported interval: {interval}"
            )

        if not 1 <= outputsize <= 5000:
            raise ValueError(
                "outputsize must be between 1 and 5000"
            )

        now = datetime.now(timezone.utc)

        interval_seconds = SUPPORTED_INTERVALS[interval]

        raw_data = self.provider.get_candles(
            symbol=symbol,
            interval=interval,
            outputsize=outputsize
        )

        # Only use candles whose closing time has passed.
        candle_close_times = (
            raw_data["timestamp"]
            + pd.to_timedelta(
                interval_seconds,
                unit="s"
            )
        )

        completed_data = raw_data.loc[
            candle_close_times <= pd.Timestamp(now)
        ].copy()

        completed_data = completed_data.sort_values(
            "timestamp"
        ).reset_index(drop=True)

        quality = self.validator.validate(
            completed_data,
            interval_seconds=interval_seconds,
            max_staleness_seconds=interval_seconds * 3,
            min_candles=1,
            now=now
        )

        
        return {
            "asset": symbol,
            "timeframe": interval,
            "source": "Twelve Data",
            "data_mode": DATA_MODE,
            "retrieved_at": now.isoformat(),
            "last_update": (
                (
                    completed_data["timestamp"].iloc[-1]
                    + pd.Timedelta(seconds=interval_seconds)
                ).isoformat()
                if not completed_data.empty
                else None
            ),
            "data": completed_data,
            "quality": quality,
        }



