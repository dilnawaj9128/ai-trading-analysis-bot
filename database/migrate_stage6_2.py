
import sqlite3
from pathlib import Path


DB_PATH = Path("data/paper_trading.db")


def migrate():
    if not DB_PATH.is_file():
        raise FileNotFoundError(
            f"Database not found: {DB_PATH}"
        )

    with sqlite3.connect(DB_PATH) as connection:
        connection.execute("BEGIN IMMEDIATE")

        columns = {
            row[1]
            for row in connection.execute(
                "PRAGMA table_info(paper_trades)"
            )
        }

        new_columns = {
            "trade_source": (
                "TEXT NOT NULL DEFAULT 'MANUAL_TEST'"
            ),
            "price_source": (
                "TEXT NOT NULL DEFAULT 'MANUAL_INPUT'"
            ),
            "expiry_price_time": "TEXT",
        }

        for name, definition in new_columns.items():
            if name not in columns:
                connection.execute(
                    f"ALTER TABLE paper_trades "
                    f"ADD COLUMN {name} {definition}"
                )
                print(f"Added column: {name}")

        print("Stage 6.2 migration completed.")


if __name__ == "__main__":
    migrate()


