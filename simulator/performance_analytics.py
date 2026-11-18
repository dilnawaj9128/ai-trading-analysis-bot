
"""
Stage 6.4: Read-only, source-aware paper trading analytics.

These reports use realized P&L from closed trades.
They do not represent broker-verified trading results.
"""

from collections import defaultdict
from datetime import datetime, timezone
from math import isfinite


SOURCES = ("MANUAL_TEST", "HISTORICAL_RESEARCH")
EXPIRIES = (1, 5, 15)


def _utc_datetime(value):
    if value is None:
        return datetime.min.replace(tzinfo=timezone.utc)

    if isinstance(value, str):
        value = datetime.fromisoformat(value)

    if value.tzinfo is None:
        raise ValueError("Trade timestamp must be timezone-aware.")

    return value.astimezone(timezone.utc)


def filter_trades(
    trades,
    source=None,
    result=None,
    expiry_minutes=None,
):
    """Filter trades without modifying the original collection."""

    if source is not None and source not in SOURCES:
        raise ValueError("Unsupported trade source.")

    if result is not None and result not in {
        "WIN", "LOSS", "PUSH", "OPEN"
    }:
        raise ValueError("Unsupported trade result.")

    if expiry_minutes is not None:
        if expiry_minutes not in EXPIRIES:
            raise ValueError("Expiry must be 1, 5, or 15 minutes.")

    filtered = []

    for trade in trades:
        if source is not None and trade.trade_source != source:
            continue

        if expiry_minutes is not None:
            if trade.expiry_minutes != expiry_minutes:
                continue

        outcome = (
            trade.result
            if trade.status == "CLOSED"
            else "OPEN"
        )

        if result is not None and outcome != result:
            continue

        filtered.append(trade)

    return sorted(
        filtered,
        key=lambda trade: (
            _utc_datetime(trade.entry_time),
            trade.trade_id,
        ),
    )


def calculate_report(trades):
    """
    Calculate statistics for a selected group of trades.

    Drawdown is based on cumulative realized P&L,
    not account equity or unrealized P&L.
    """

    trades = list(trades)

    closed = [
        trade for trade in trades
        if trade.status == "CLOSED"
    ]

    open_trades = [
        trade for trade in trades
        if trade.status == "OPEN"
    ]

    wins = sum(t.result == "WIN" for t in closed)
    losses = sum(t.result == "LOSS" for t in closed)
    pushes = sum(t.result == "PUSH" for t in closed)

    pnl_values = [
        float(t.profit_loss)
        for t in closed
    ]

    if not all(isfinite(pnl) for pnl in pnl_values):
        raise ValueError("Invalid trade profit/loss value.")

    total_pnl = sum(pnl_values)
    closed_count = len(closed)

    decided = wins + losses

    win_rate = (
        wins / decided * 100
        if decided else 0.0
    )

    average_pnl = (
        total_pnl / closed_count
        if closed_count else 0.0
    )

    gross_profit = sum(
        max(pnl, 0.0) for pnl in pnl_values
    )

    gross_loss = abs(sum(
        min(pnl, 0.0) for pnl in pnl_values
    ))

    profit_factor = (
        gross_profit / gross_loss
        if gross_loss > 0 else None
    )

    # Sort by settlement time to avoid using future outcomes
    # before earlier realized outcomes.
    ordered = sorted(
        closed,
        key=lambda trade: (
            _utc_datetime(trade.exit_time),
            trade.trade_id,
        ),
    )

    cumulative_pnl = 0.0
    peak_pnl = 0.0
    maximum_drawdown = 0.0

    for trade in ordered:
        cumulative_pnl += float(trade.profit_loss)
        peak_pnl = max(peak_pnl, cumulative_pnl)

        drawdown = peak_pnl - cumulative_pnl

        maximum_drawdown = max(
            maximum_drawdown, drawdown
        )

    return {
        "total_trades": len(trades),
        "closed_trades": closed_count,
        "open_trades": len(open_trades),
        "wins": wins,
        "losses": losses,
        "pushes": pushes,
        "win_rate": win_rate,
        "total_pnl": total_pnl,
        "average_pnl": average_pnl,
        "gross_profit": gross_profit,
        "gross_loss": gross_loss,
        "profit_factor": profit_factor,
        "maximum_drawdown": maximum_drawdown,
    }


def build_performance_reports(trades):
    """
    Build overall, source-specific, and expiry-specific reports.
    """

    trades = list(trades)

    reports = {
        "overall": calculate_report(trades),
        "sources": {},
        "expiry": {},
        "source_expiry": {},
    }

    for source in SOURCES:
        source_trades = filter_trades(
            trades, source=source
        )

        reports["sources"][source] = calculate_report(
            source_trades
        )

        reports["source_expiry"][source] = {}

        for expiry in EXPIRIES:
            subset = filter_trades(
                source_trades,
                expiry_minutes=expiry,
            )

            reports["source_expiry"][source][expiry] = (
                calculate_report(subset)
            )

    for expiry in EXPIRIES:
        reports["expiry"][expiry] = calculate_report(
            filter_trades(
                trades,
                expiry_minutes=expiry,
            )
        )

    return reports


def print_report(title, report):
    """Display a performance report in the terminal."""

    print()
    print("=" * 54)
    print(title)
    print("=" * 54)

    print(f"Total Trades       : {report['total_trades']}")
    print(f"Closed Trades      : {report['closed_trades']}")
    print(f"Open Trades        : {report['open_trades']}")
    print(f"Wins               : {report['wins']}")
    print(f"Losses             : {report['losses']}")
    print(f"Pushes             : {report['pushes']}")
    print(f"Win Rate           : {report['win_rate']:.2f}%")
    print(f"Total P&L          : {report['total_pnl']:.2f}")
    print(f"Average P&L        : {report['average_pnl']:.2f}")
    print(f"Gross Profit       : {report['gross_profit']:.2f}")
    print(f"Gross Loss         : {report['gross_loss']:.2f}")

    factor = report["profit_factor"]

    if factor is None:
        print("Profit Factor      : N/A (no gross losses)")
    else:
        print(f"Profit Factor      : {factor:.2f}")

    print(
        "Max Realized P&L "
        f"Drawdown: {report['maximum_drawdown']:.2f}"
    )

    print("=" * 54)


def print_trade_history(trades):
    trades = list(trades)

    print()
    print("=" * 90)
    print("FILTERED PAPER TRADE HISTORY")
    print("=" * 90)

    if not trades:
        print("No matching trades.")
        return

    for trade in trades:
        print(f"Trade ID     : {trade.trade_id}")
        print(f"Source       : {trade.trade_source}")
        print(f"Direction    : {trade.direction}")
        print(f"Expiry       : {trade.expiry_minutes} min")
        print(f"Status       : {trade.status}")
        print(f"Result       : {trade.result or 'OPEN'}")
        print(f"Entry Price  : {trade.entry_price}")
        print(f"Exit Price   : {trade.exit_price}")
        print(f"P&L          : {trade.profit_loss:.2f}")
        print(f"Price Source : {trade.price_source}")
        print(f"Entry Time   : {trade.entry_time}")
        print(f"Exit Time    : {trade.exit_time}")
        print("-" * 90)

