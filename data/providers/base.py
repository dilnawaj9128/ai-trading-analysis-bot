
from abc import ABC, abstractmethod

import pandas as pd


class MarketDataProvider(ABC):

    @abstractmethod
    def get_candles(
        self,
        symbol: str,
        interval: str,
        outputsize: int = 500
    ) -> pd.DataFrame:
        """
        Retrieve OHLC candles.

        Returns:
            DataFrame with UTC timestamps and
            Open, High, Low, Close, Volume columns.
        """
        pass
