
from data.market_data import MarketDataService


class HistoricalDataService:

    def __init__(self):
        self.market_service = MarketDataService()

    def fetch_history(
        self,
        symbol="EUR/USD",
        interval="5min",
        candles=1000
    ):

        result = self.market_service.get_market_data(
            symbol=symbol,
            interval=interval,
            outputsize=candles
        )

        return {
            "asset": result["asset"],
            "timeframe": result["timeframe"],
            "source": result["source"],
            "data_mode": result["data_mode"],
            "quality": result["quality"],
            "candles": result["data"]
        }

