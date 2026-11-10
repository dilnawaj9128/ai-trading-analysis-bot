
import requests
import pandas as pd

from datetime import timezone

from config import (
    API_KEY,
    BASE_URL,
    API_TIMEOUT
)

from data.providers.base import MarketDataProvider


class TwelveDataProvider(MarketDataProvider):

    def __init__(self):
        if not API_KEY:
            raise ValueError(
                "TWELVE_DATA_API_KEY is missing. "
                "Configure your .env file."
            )

        self.session = requests.Session()

    def get_candles(
        self,
        symbol: str,
        interval: str,
        outputsize: int = 500
    ) -> pd.DataFrame:

        endpoint = f"{BASE_URL}/time_series"

        params = {
            "symbol": symbol,
            "interval": interval,
            "outputsize": outputsize,
            "apikey": API_KEY,
            "timezone": "UTC",
            "format": "JSON"
        }

        try:
            response = self.session.get(
                endpoint,
                params=params,
                timeout=API_TIMEOUT
            )

            response.raise_for_status()

            result = response.json()

        except requests.RequestException as exc:
            raise RuntimeError(
                f"Market data request failed: {exc}"
            ) from exc

        except ValueError as exc:
            raise RuntimeError(
                "Provider returned invalid JSON"
            ) from exc

        if result.get("status") == "error":
            raise RuntimeError(
                f"Twelve Data error: "
                f"{result.get('message', 'Unknown error')}"
            )

        values = result.get("values")

        if not values:
            raise RuntimeError(
                "No market candles returned by provider"
            )

        df = pd.DataFrame(values)

        required = [
            "datetime",
            "open",
            "high",
            "low",
            "close"
        ]

        missing = set(required) - set(df.columns)

        if missing:
            raise RuntimeError(
                f"Missing provider fields: {missing}"
            )

        df["timestamp"] = pd.to_datetime(
            df["datetime"],
            utc=True,
            errors="coerce"
        )

        for column in [
            "open",
            "high",
            "low",
            "close"
        ]:
            df[column] = pd.to_numeric(
                df[column],
                errors="coerce"
            )

        if "volume" in df.columns:
            df["volume"] = pd.to_numeric(
                df["volume"],
                errors="coerce"
            )
        else:
            # Forex volume may not be supplied.
            df["volume"] = float("nan")

        df = df.rename(
            columns={
                "open": "Open",
                "high": "High",
                "low": "Low",
                "close": "Close",
                "volume": "Volume"
            }
        )

        df = df[
            [
                "timestamp",
                "Open",
                "High",
                "Low",
                "Close",
                "Volume"
            ]
        ]

        df = df.sort_values("timestamp")

        df = df.reset_index(drop=True)

        return df

