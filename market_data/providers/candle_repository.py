import math
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


class CandleRepository:
    def __init__(self, db_path="data/quotex_market_data.db"):
        self.db_path = str(db_path)
        Path(self.db_path).parent.mkdir(
            parents=True, exist_ok=True
        )
        self._initialize()

    def _connect(self):
        return sqlite3.connect(self.db_path)

    def _initialize(self):
        with self._connect() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS candles (
                    source TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    timeframe TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    open REAL NOT NULL,
                    high REAL NOT NULL,
                    low REAL NOT NULL,
                    close REAL NOT NULL,
                    PRIMARY KEY (
                        source, symbol,
                        timeframe, timestamp
                    )
                )
            """)

    def save_candle(
        self,
        candle,
        symbol="EURUSD_otc",
        source="SIMULATED",
    ):
        timestamp = candle["timestamp"]

        if not isinstance(timestamp, datetime):
            raise ValueError("Expected datetime timestamp")

        if timestamp.tzinfo is None:
            raise ValueError("Timestamp must be UTC-aware")

        timestamp = timestamp.astimezone(timezone.utc)

        if timestamp.second or timestamp.microsecond:
            raise ValueError("Timestamp must be minute-aligned")

        prices = [
            float(candle[k])
            for k in ("open", "high", "low", "close")
        ]

        o, h, l, c = prices

        if not all(math.isfinite(p) and p > 0 for p in prices):
            raise ValueError("Invalid OHLC price")

        if h < max(o, c, l) or l > min(o, c, h):
            raise ValueError("Inconsistent OHLC candle")

        with self._connect() as conn:
            cursor = conn.execute("""
                INSERT OR IGNORE INTO candles
                (source, symbol, timeframe, timestamp,
                 open, high, low, close)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                source, symbol, "1min",
                timestamp.isoformat(),
                o, h, l, c
            ))
            return cursor.rowcount == 1

    def count_candles(self):
        with self._connect() as conn:
            return conn.execute(
                "SELECT COUNT(*) FROM candles"
            ).fetchone()[0]
