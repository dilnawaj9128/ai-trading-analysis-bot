from datetime import datetime, timezone


def calculate_performance_metrics(trades, initial_balance):
    if initial_balance <= 0:
        raise ValueError("Initial balance must be positive.")

    trades = list(trades)

    open_trades = [
        trade for trade in trades
        if trade.status == "OPEN"
    ]

    closed_trades = [
        trade for trade in trades
        if trade.status == "CLOSED"
    ]

    wins = [t for t in closed_trades if t.result == "WIN"]
    losses = [t for t in closed_trades if t.result == "LOSS"]
    pushes = [t for t in closed_trades if t.result == "PUSH"]

    total_profit_loss = sum(
        float(trade.profit_loss) for trade in closed_trades
    )

    decided_trades = len(wins) + len(losses)

    win_rate = (
        (len(wins) / decided_trades) * 100
        if decided_trades else 0.0
    )

    average_profit_loss = (
        total_profit_loss / len(closed_trades)
        if closed_trades else 0.0
    )

    # Calculate realized equity chronologically.
    def sort_time(trade):
        value = trade.exit_time or trade.entry_time
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    ordered_trades = sorted(closed_trades, key=sort_time)

    equity = float(initial_balance)
    peak_equity = equity
    max_drawdown = 0.0
    max_drawdown_pct = 0.0

    for trade in ordered_trades:
        equity += float(trade.profit_loss)
        peak_equity = max(peak_equity, equity)

        drawdown = peak_equity - equity
        drawdown_pct = (
            (drawdown / peak_equity) * 100
            if peak_equity > 0 else 0.0
        )

        max_drawdown = max(max_drawdown, drawdown)
        max_drawdown_pct = max(max_drawdown_pct, drawdown_pct)

    return {
        "initial_balance": float(initial_balance),
        "total_trades": len(trades),
        "closed_trades": len(closed_trades),
        "open_trades": len(open_trades),
        "wins": len(wins),
        "losses": len(losses),
        "pushes": len(pushes),
        "decided_trades": decided_trades,
        "win_rate_pct": win_rate,
        "total_profit_loss": total_profit_loss,
        "average_profit_loss": average_profit_loss,
        "ending_realized_balance": (
            float(initial_balance) + total_profit_loss
        ),
        "max_drawdown": max_drawdown,
        "max_drawdown_pct": max_drawdown_pct,
    }


def print_performance_report(metrics):
    print("\n" + "=" * 45)
    print("       PAPER TRADING PERFORMANCE")
    print("=" * 45)

    print(f"Initial Balance       : {metrics['initial_balance']:.2f}")
    print(f"Total Trades          : {metrics['total_trades']}")
    print(f"Closed Trades         : {metrics['closed_trades']}")
    print(f"Open Trades           : {metrics['open_trades']}")
    print(f"Wins                  : {metrics['wins']}")
    print(f"Losses                : {metrics['losses']}")
    print(f"Pushes                : {metrics['pushes']}")
    print(f"Win Rate              : {metrics['win_rate_pct']:.2f}%")
    print(f"Total Profit / Loss   : {metrics['total_profit_loss']:.2f}")
    print(f"Average P&L / Trade   : {metrics['average_profit_loss']:.2f}")
    print(
        f"Ending Realized Balance: "
        f"{metrics['ending_realized_balance']:.2f}"
    )
    print(f"Maximum Drawdown      : {metrics['max_drawdown']:.2f}")
    print(f"Maximum Drawdown %    : {metrics['max_drawdown_pct']:.2f}%")
    print("=" * 45)
