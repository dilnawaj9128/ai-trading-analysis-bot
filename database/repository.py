
from datetime import datetime

from database.db import Database
from database.models import StoredTrade


class PaperTradingRepository:

    def __init__(self, db_path="data/paper_trading.db"):
        self.database = Database(db_path)

    def get_or_create_account(self, initial_balance):
        with self.database.connect() as connection:
            connection.execute(
                """
                INSERT OR IGNORE INTO paper_account
                (id, initial_balance, balance)
                VALUES (1, ?, ?)
                """,
                (float(initial_balance), float(initial_balance)),
            )

            row = connection.execute(
                """
                SELECT initial_balance, balance
                FROM paper_account WHERE id = 1
                """
            ).fetchone()

            return (
                float(row["initial_balance"]),
                float(row["balance"]),
            )

    def get_balance(self):
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT balance FROM paper_account WHERE id = 1"
            ).fetchone()

            if row is None:
                raise ValueError("Paper account does not exist.")

            return float(row["balance"])

    def save_open_trade(self, trade, new_balance):
        with self.database.connect() as connection:
            connection.execute(
                """
                INSERT INTO paper_trades (
                    trade_id, direction, entry_price, stake,
                    payout_rate, expiry_minutes, entry_time,
                    status, exit_price, exit_time, result,
                    profit_loss, trade_source, price_source,
                    expiry_price_time
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    trade.trade_id,
                    trade.direction,
                    trade.entry_price,
                    trade.stake,
                    trade.payout_rate,
                    trade.expiry_minutes,
                    trade.entry_time.isoformat(),
                    trade.status,
                    trade.exit_price,
                    (
                        trade.exit_time.isoformat()
                        if trade.exit_time else None
                    ),
                    trade.result,
                    trade.profit_loss,
                    trade.trade_source,
                    trade.price_source,
                    (
                        trade.expiry_price_time.isoformat()
                        if trade.expiry_price_time else None
                    ),
                ),
            )

            cursor = connection.execute(
                "UPDATE paper_account SET balance = ? WHERE id = 1",
                (float(new_balance),),
            )

            if cursor.rowcount != 1:
                raise ValueError("Paper account does not exist.")

    def save_settled_trade(self, trade, new_balance):
        with self.database.connect() as connection:
            cursor = connection.execute(
                """
                UPDATE paper_trades
                SET status = ?, exit_price = ?, exit_time = ?,
                    result = ?, profit_loss = ?,
                    price_source = ?, expiry_price_time = ?
                WHERE trade_id = ? AND status = 'OPEN'
                """,
                (
                    trade.status,
                    trade.exit_price,
                    trade.exit_time.isoformat(),
                    trade.result,
                    trade.profit_loss,
                    trade.price_source,
                    (
                        trade.expiry_price_time.isoformat()
                        if trade.expiry_price_time else None
                    ),
                    trade.trade_id,
                ),
            )

            if cursor.rowcount != 1:
                raise ValueError(
                    "Trade was not found or already settled."
                )

            cursor = connection.execute(
                "UPDATE paper_account SET balance = ? WHERE id = 1",
                (float(new_balance),),
            )

            if cursor.rowcount != 1:
                raise ValueError("Paper account does not exist.")

    def get_all_trades(self):
        with self.database.connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM paper_trades
                ORDER BY entry_time ASC
                """
            ).fetchall()

        return [
            StoredTrade(
                trade_id=row["trade_id"],
                direction=row["direction"],
                entry_price=row["entry_price"],
                stake=row["stake"],
                payout_rate=row["payout_rate"],
                expiry_minutes=row["expiry_minutes"],
                entry_time=datetime.fromisoformat(
                    row["entry_time"]
                ),
                status=row["status"],
                exit_price=row["exit_price"],
                exit_time=(
                    datetime.fromisoformat(row["exit_time"])
                    if row["exit_time"] else None
                ),
                result=row["result"],
                profit_loss=row["profit_loss"],
                trade_source=row["trade_source"],
                price_source=row["price_source"],
                expiry_price_time=(
                    datetime.fromisoformat(
                        row["expiry_price_time"]
                    )
                    if row["expiry_price_time"] else None
                ),
            )
            for row in rows
        ]

