
from database.repository import PaperTradingRepository


def show_trade_history():
    repository = PaperTradingRepository()

    trades = repository.get_all_trades()

    print("\n" + "=" * 65)
    print("PAPER TRADING HISTORY")
    print("=" * 65)

    if not trades:
        print("No trades found.")
        return

    for trade in trades:
        print("-" * 65)
        print("Trade ID:", trade.trade_id)
        print("Direction:", trade.direction)
        print("Entry Price:", trade.entry_price)
        print("Exit Price:", trade.exit_price)
        print("Stake:", trade.stake)
        print("Expiry:", trade.expiry_minutes, "minutes")
        print("Entry Time:", trade.entry_time)
        print("Exit Time:", trade.exit_time)
        print("Status:", trade.status)
        print("Result:", trade.result)
        print("Profit/Loss:", f"{trade.profit_loss:.2f}")

        # Newly migrated database metadata
        with repository.database.connect() as connection:
            row = connection.execute(
                """
                SELECT trade_source, price_source,
                       expiry_price_time
                FROM paper_trades
                WHERE trade_id = ?
                """,
                (trade.trade_id,),
            ).fetchone()

        if row:
            print("Trade Source:", row["trade_source"])
            print("Price Source:", row["price_source"])
            print("Expiry Price Time:", row["expiry_price_time"])

    print("=" * 65)


if __name__ == "__main__":
    show_trade_history()

