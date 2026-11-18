
from datetime import datetime, timedelta, timezone

from database.repository import PaperTradingRepository
from simulator import (
    PaperTradingSimulator,
    calculate_performance_metrics,
    print_performance_report,
)


def read_positive_float(prompt):
    while True:
        try:
            value = float(input(prompt))

            if value <= 0:
                print("Value must be greater than zero.")
                continue

            return value

        except ValueError:
            print("Please enter a valid number.")


def read_expiry():
    while True:
        try:
            expiry = int(input("Expiry (1, 5, or 15 minutes): "))

            if expiry not in (1, 5, 15):
                print("Choose 1, 5, or 15 minutes.")
                continue

            return expiry

        except ValueError:
            print("Please enter a valid integer.")


def show_open_trades(simulator):

    open_trades = [
        trade for trade in simulator.trades
        if trade.status == "OPEN"
    ]

    print("\n========== OPEN PAPER TRADES ==========")

    if not open_trades:
        print("No open trades.")
        return

    for trade in open_trades:

        expiry_time = (
            trade.entry_time
            + timedelta(minutes=trade.expiry_minutes)
        )

        print("-" * 45)
        print("Trade ID:", trade.trade_id)
        print("Direction:", trade.direction)
        print("Entry Price:", trade.entry_price)
        print("Stake:", trade.stake)
        print("Expiry:", trade.expiry_minutes, "minutes")
        print("Entry Time:", trade.entry_time)
        print("Expiry Time:", expiry_time)


def open_manual_trade(simulator):

    print("\n========== OPEN MANUAL PAPER TRADE ==========")
    print("This is a manual simulation, not a live signal.")

    direction_choice = input("Direction (UP/DOWN): ").strip().upper()

    if direction_choice not in ("UP", "DOWN"):
        print("Invalid direction.")
        return

    entry_price = read_positive_float("Entry price: ")
    stake = read_positive_float("Stake amount: ")
    expiry = read_expiry()

    payout_input = input("Payout rate (default 0.80): ").strip()

    try:
        payout_rate = float(payout_input) if payout_input else 0.80
    except ValueError:
        print("Invalid payout rate.")
        return

    if not 0 < payout_rate <= 1:
        print("Payout rate must be greater than 0 and at most 1.")
        return

    confirm = input(
        f"Confirm manual {direction_choice} paper trade? (y/n): "
    ).strip().lower()

    if confirm != "y":
        print("Trade cancelled.")
        return

    trade = simulator.open_trade(
        signal=direction_choice,
        entry_price=entry_price,
        stake=stake,
        expiry_minutes=expiry,
        entry_time=datetime.now(timezone.utc),
        payout_rate=payout_rate,
        data_quality_status="VALID",
    )

    print("\nPaper trade opened successfully.")
    print("Trade ID:", trade.trade_id)
    print("Direction:", trade.direction)
    print("Entry Price:", trade.entry_price)
    print("Stake:", trade.stake)
    print("Expiry:", trade.expiry_minutes, "minutes")
    print("Available Balance:", f"{simulator.balance:.2f}")


def settle_manual_trade(simulator):

    open_trades = [
        trade for trade in simulator.trades
        if trade.status == "OPEN"
    ]

    print("\n========== SETTLE PAPER TRADE ==========")

    if not open_trades:
        print("No open trades available.")
        return

    show_open_trades(simulator)

    trade_id = input("\nEnter Trade ID to settle: ").strip()

    trade = next(
        (t for t in open_trades if t.trade_id == trade_id),
        None,
    )

    if trade is None:
        print("Trade ID not found.")
        return

    now = datetime.now(timezone.utc)

    expiry_time = (
        trade.entry_time
        + timedelta(minutes=trade.expiry_minutes)
    )

    if now < expiry_time:
        remaining = expiry_time - now
        print("Trade has not expired yet.")
        print("Remaining time:", remaining)
        return

    exit_price = read_positive_float("Enter exit price: ")

    settled_trade = simulator.settle_trade(
        trade_id=trade.trade_id,
        exit_price=exit_price,
        exit_time=now,
    )

    print("\n========== SETTLEMENT RESULT ==========")
    print("Trade ID:", settled_trade.trade_id)
    print("Direction:", settled_trade.direction)
    print("Entry Price:", settled_trade.entry_price)
    print("Exit Price:", settled_trade.exit_price)
    print("Result:", settled_trade.result)
    print("Profit / Loss:", f"{settled_trade.profit_loss:.2f}")
    print("Available Balance:", f"{simulator.balance:.2f}")


def show_performance(simulator):

    metrics = calculate_performance_metrics(
        simulator.trades,
        simulator.initial_balance,
    )

    print_performance_report(metrics)

    print(
        "Available Paper Balance:",
        f"{simulator.balance:.2f}",
    )


def main():

    repository = PaperTradingRepository()

    simulator = PaperTradingSimulator(
        repository=repository
    )

    while True:

        print("\n")
        print("=" * 45)
        print("PAPER TRADING MANAGEMENT")
        print("=" * 45)
        print("1. Open Manual Paper Trade")
        print("2. View Open Trades")
        print("3. Settle Expired Trade")
        print("4. View Performance Report")
        print("0. Exit")
        print("=" * 45)

        choice = input("Choose an option: ").strip()

        try:

            if choice == "1":
                open_manual_trade(simulator)

            elif choice == "2":
                show_open_trades(simulator)

            elif choice == "3":
                settle_manual_trade(simulator)

            elif choice == "4":
                show_performance(simulator)

            elif choice == "0":
                print("Exiting Paper Trading Management.")
                break

            else:
                print("Invalid option. Try again.")

        except (ValueError, RuntimeError) as error:
            print("Operation failed:", error)

        except Exception as error:
            print("Unexpected error:", error)


if __name__ == "__main__":
    main()

