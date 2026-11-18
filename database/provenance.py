
"""Research provenance storage, separate from legacy trades."""

from dataclasses import dataclass
from datetime import datetime
import sqlite3

from database.db import Database


@dataclass(frozen=True)
class ResearchProvenanceRecord:
    trade_id: str
    provider: str
    feed_mode: str
    symbol: str
    timeframe: str
    retrieved_at: datetime
    validation_version: str = "6.5.2"


class ResearchProvenanceRepository:
    def __init__(self, db_path="data/paper_trading.db"):
        self.database = Database(db_path)

        with self.database.connect() as connection:
            connection.execute("""
                CREATE TABLE IF NOT EXISTS research_provenance (
                    trade_id TEXT PRIMARY KEY,
                    provider TEXT NOT NULL,
                    feed_mode TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    timeframe TEXT NOT NULL,
                    retrieved_at TEXT NOT NULL,
                    validation_version TEXT NOT NULL,
                    FOREIGN KEY (trade_id)
                        REFERENCES paper_trades(trade_id)
                )
            """)

    def save(self, record):
        if not isinstance(record, ResearchProvenanceRecord):
            raise ValueError("Invalid provenance record.")

        with self.database.connect() as connection:
            connection.execute(
                """
                INSERT INTO research_provenance (
                    trade_id, provider, feed_mode, symbol,
                    timeframe, retrieved_at, validation_version
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.trade_id,
                    record.provider,
                    record.feed_mode,
                    record.symbol,
                    record.timeframe,
                    record.retrieved_at.isoformat(),
                    record.validation_version,
                ),
            )

    def get(self, trade_id):
        with self.database.connect() as connection:
            row = connection.execute(
                """
                SELECT * FROM research_provenance
                WHERE trade_id = ?
                """,
                (trade_id,),
            ).fetchone()

        if row is None:
            return None

        return ResearchProvenanceRecord(
            trade_id=row["trade_id"],
            provider=row["provider"],
            feed_mode=row["feed_mode"],
            symbol=row["symbol"],
            timeframe=row["timeframe"],
            retrieved_at=datetime.fromisoformat(
                row["retrieved_at"]
            ),
            validation_version=row["validation_version"],
        )

    def count(self):
        with self.database.connect() as connection:
            return connection.execute(
                "SELECT COUNT(*) FROM research_provenance"
            ).fetchone()[0]

