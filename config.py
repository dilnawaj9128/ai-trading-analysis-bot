
import os
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv("TWELVE_DATA_API_KEY")

DATA_MODE = os.getenv("DATA_MODE", "unknown").lower()

DEFAULT_SYMBOL = os.getenv("DEFAULT_SYMBOL", "EUR/USD")
DEFAULT_INTERVAL = os.getenv("DEFAULT_INTERVAL", "1min")

OUTPUT_SIZE = int(os.getenv("OUTPUT_SIZE", "500"))
API_TIMEOUT = int(os.getenv("API_TIMEOUT", "20"))

BASE_URL = "https://api.twelvedata.com"

SUPPORTED_SYMBOLS = [
    "EUR/USD",
    "GBP/USD",
    "USD/JPY",
]

SUPPORTED_INTERVALS = {
    "1min": 60,
    "5min": 300,
    "15min": 900,
}

if DATA_MODE not in {"live", "delayed", "simulated", "unknown"}:
    raise ValueError("Invalid DATA_MODE")

if OUTPUT_SIZE < 1 or OUTPUT_SIZE > 5000:
    raise ValueError("OUTPUT_SIZE must be between 1 and 5000")

