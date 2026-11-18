
import sqlite3
from pathlib import Path


class Database:
    def __init__(self, db_path="data/paper_trading.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.initialize()

    def connect(self):
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def initialize(self):
        with self.connect() as connection:
            connection.execute("""
                CREATE TABLE IF NOT EXISTS paper_account (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    initial_balance REAL NOT NULL,
                    balance REAL NOT NULL
                )
            """)

            connection.execute("""
                CREATE TABLE IF NOT EXISTS paper_trades (
                    trade_id TEXT PRIMARY KEY,
                    direction TEXT NOT NULL,
                    entry_price REAL NOT NULL,
                    stake REAL NOT NULL,
                    payout_rate REAL NOT NULL,
                    expiry_minutes INTEGER NOT NULL,
                    entry_time TEXT NOT NULL,
                    status TEXT NOT NULL,
                    exit_price REAL,
                    exit_time TEXT,
                    result TEXT,
                    profit_loss REAL NOT NULL DEFAULT 0,
                    trade_source TEXT NOT NULL
                        DEFAULT 'MANUAL_TEST',
                    price_source TEXT NOT NULL
                        DEFAULT 'MANUAL_INPUT',
                    expiry_price_time TEXT
                )
            """)

            # Upgrade older databases without deleting records.
            columns = {
                row["name"]
                for row in connection.execute(
                    "PRAGMA table_info(paper_trades)"
                )
            }

            additions = {
                "trade_source":
                    "TEXT NOT NULL DEFAULT 'MANUAL_TEST'",
                "price_source":
                    "TEXT NOT NULL DEFAULT 'MANUAL_INPUT'",
                "expiry_price_time": "TEXT",
            }

            for name, definition in additions.items():
                if name not in columns:
                    connection.execute(
                        f"ALTER TABLE paper_trades "
                        f"ADD COLUMN {name} {definition}"
                    )

            connection.execute("""
                CREATE INDEX IF NOT EXISTS idx_paper_trades_status
                ON paper_trades(status)
            """)

