
"""Stage 6.6: in-memory historical backtesting.

Research only. No broker orders and no SQLite writes.
"""

from dataclasses import dataclass
from datetime import timedelta
from math import isfinite

from indicators import calculate_indicators
from patterns import detect_candlestick_patterns
from strategy.signal_engine import generate_signal
from simulator.historical_integrity import (
    HistoricalProvenance,
    normalize_candles,
    validate_historical_trade,
)


@dataclass(frozen=True)
class BacktestTrade:
    direction: str
    entry_time: object
    expiry_time: object
    entry_price: float
    expiry_price: float
    expiry_minutes: int
    result: str
    profit_loss: float


@dataclass(frozen=True)
class BacktestReport:
    trades: list
    signals_checked: int
    no_trade_count: int
    wins: int
    losses: int
    pushes: int
    total_pnl: float
    win_rate: float
    max_drawdown: float


def run_backtest(
    candles,
    provenance: HistoricalProvenance,
    *,
    expiry_minutes=15,
    stake=50.0,
    payout_rate=0.80,
    warmup_candles=50,
):
    """
    Run a non-overlapping historical backtest.

    Candle timestamp means candle OPEN time.
    At entry T, only candles ending at or before T
    are available to the signal engine.

    The entry is simulated at the Open of candle T.
    This is an idealized research fill, not an
    executable or broker-verified quote.
    """

    if expiry_minutes not in (1, 5, 15):
        raise ValueError("Expiry must be 1, 5, or 15.")

    if warmup_candles < 50:
        raise ValueError("At least 50 warmup candles required.")

    if not isfinite(float(stake)) or stake <= 0:
        raise ValueError("Stake must be positive and finite.")

    if not isfinite(float(payout_rate)) or not 0 < payout_rate <= 1:
        raise ValueError("Payout rate must be between 0 and 1.")

    mode = str(provenance.feed_mode).strip().lower()

    if mode not in {"live", "delayed"}:
        raise ValueError(
            "Backtesting requires independently verified "
            "live or delayed feed provenance."
        )

    # Validate every supplied candle before analysis.
    data = normalize_candles(candles).reset_index(drop=True)

    # Reject gaps across the entire dataset.
    if len(data) > 1:
        gaps = data["timestamp"].diff().iloc[1:]
        if not gaps.eq(timedelta(minutes=1)).all():
            raise ValueError(
                "Historical dataset contains missing minute candles."
            )

    trades = []
    checked = 0
    no_trade_count = 0
    equity = 0.0
    equity_peak = 0.0
    max_drawdown = 0.0

    index = warmup_candles

    while index + expiry_minutes <= len(data):
        entry_time = data.iloc[index]["timestamp"]

        # At T, the candle starting at T is NOT completed.
        # Every candle here ended at or before T.
        completed = data.iloc[:index].copy()

        # No future rows are passed to any indicator,
        # candlestick detector or signal generator.
        indicators = calculate_indicators(completed)
        patterns = detect_candlestick_patterns(indicators)

        signal_result = generate_signal(
            patterns,
            expiry_minutes=expiry_minutes,
            data_mode=mode,
            data_quality_status="VALID",
        )

        checked += 1
        signal = signal_result["signal"]

        if signal == "NO TRADE":
            no_trade_count += 1
            index += 1
            continue

        if signal not in {"UP", "DOWN"}:
            raise ValueError("Unexpected strategy signal.")

        validated = validate_historical_trade(
            candles=data,
            entry_time=entry_time,
            expiry_minutes=expiry_minutes,
            provenance=provenance,
        )

        entry_price = validated.entry_price
        expiry_price = validated.expiry_price

        if entry_price == expiry_price:
            result = "PUSH"
            pnl = 0.0
        elif (
            (signal == "UP" and expiry_price > entry_price)
            or (signal == "DOWN" and expiry_price < entry_price)
        ):
            result = "WIN"
            pnl = float(stake) * float(payout_rate)
        else:
            result = "LOSS"
            pnl = -float(stake)

        trades.append(
            BacktestTrade(
                direction=signal,
                entry_time=validated.entry_time,
                expiry_time=validated.expiry_time,
                entry_price=entry_price,
                expiry_price=expiry_price,
                expiry_minutes=expiry_minutes,
                result=result,
                profit_loss=pnl,
            )
        )

        equity += pnl
        equity_peak = max(equity_peak, equity)
        max_drawdown = max(
            max_drawdown, equity_peak - equity
        )

        # One position at a time. The next possible
        # entry is at or after this trade's expiry.
        index += expiry_minutes

    wins = sum(t.result == "WIN" for t in trades)
    losses = sum(t.result == "LOSS" for t in trades)
    pushes = sum(t.result == "PUSH" for t in trades)

    decisive = wins + losses

    return BacktestReport(
        trades=trades,
        signals_checked=checked,
        no_trade_count=no_trade_count,
        wins=wins,
        losses=losses,
        pushes=pushes,
        total_pnl=round(equity, 2),
        win_rate=round(
            100.0 * wins / decisive, 2
        ) if decisive else 0.0,
        max_drawdown=round(max_drawdown, 2),
    )


def print_backtest_report(report):
    print("\n" + "=" * 50)
    print("STAGE 6.6 - HISTORICAL BACKTEST")
    print("=" * 50)
    print("Research only; not broker verified.")
    print(f"Signals checked : {report.signals_checked}")
    print(f"NO TRADE signals: {report.no_trade_count}")
    print(f"Closed trades   : {len(report.trades)}")
    print(f"Wins            : {report.wins}")
    print(f"Losses          : {report.losses}")
    print(f"Pushes          : {report.pushes}")
    print(f"Win rate        : {report.win_rate:.2f}%")
    print(f"Total P&L       : {report.total_pnl:.2f}")
    print(f"Max drawdown    : {report.max_drawdown:.2f}")
    print("=" * 50)

