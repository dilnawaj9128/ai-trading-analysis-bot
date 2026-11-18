from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from math import isfinite
from uuid import uuid4


@dataclass
class PaperTrade:
    trade_id: str
    direction: str
    entry_price: float
    stake: float
    payout_rate: float
    expiry_minutes: int
    entry_time: datetime
    status: str = "OPEN"
    exit_price: float | None = None
    exit_time: datetime | None = None
    result: str | None = None
    profit_loss: float = 0.0
    trade_source: str = "MANUAL_TEST"
    price_source: str = "MANUAL_INPUT"
    expiry_price_time: datetime | None = None


class PaperTradingSimulator:
    def __init__(self, initial_balance=10000.0, repository=None):
        if not isfinite(float(initial_balance)) or initial_balance <= 0:
            raise ValueError("Initial balance must be positive and finite.")
        self.repository = repository
        self.trades = []
        if repository is None:
            self.initial_balance = float(initial_balance)
            self.balance = float(initial_balance)
        else:
            self.initial_balance, self.balance = repository.get_or_create_account(initial_balance)
            self.trades = [PaperTrade(**vars(t)) for t in repository.get_all_trades()]

    def open_trade(
        self, signal, entry_price, stake, expiry_minutes, entry_time,
        payout_rate=0.80, data_quality_status="VALID", trade_source="MANUAL_TEST",
    ):
        signal = str(signal).upper()
        if signal == "NO TRADE":
            raise ValueError("Cannot open a trade for NO TRADE signal.")
        if signal not in {"UP", "DOWN"}:
            raise ValueError("Signal must be UP or DOWN.")
        if data_quality_status != "VALID":
            raise ValueError("Cannot trade with invalid or stale data.")
        if expiry_minutes not in (1, 5, 15):
            raise ValueError("Expiry must be 1, 5, or 15 minutes.")
        for name, value in (("Entry price", entry_price), ("Stake", stake)):
            if not isfinite(float(value)) or value <= 0:
                raise ValueError(f"{name} must be positive and finite.")
        if stake > self.balance:
            raise ValueError("Insufficient paper balance.")
        if not isfinite(float(payout_rate)) or not 0 < payout_rate <= 1:
            raise ValueError("Invalid payout rate.")
        if not isinstance(entry_time, datetime) or entry_time.tzinfo is None or entry_time.utcoffset() is None:
            raise ValueError("Entry time must be timezone-aware.")
        if trade_source not in {"MANUAL_TEST", "HISTORICAL_RESEARCH"}:
            raise ValueError("Unsupported trade source.")
        entry_time = entry_time.astimezone(timezone.utc)
        if trade_source == "HISTORICAL_RESEARCH" and (entry_time.second or entry_time.microsecond):
            raise ValueError("Historical entry must align to a minute boundary.")

        trade = PaperTrade(
            trade_id=str(uuid4()), direction=signal, entry_price=float(entry_price),
            stake=float(stake), payout_rate=float(payout_rate),
            expiry_minutes=expiry_minutes, entry_time=entry_time,
            trade_source=trade_source,
            price_source=("HISTORICAL_CANDLE" if trade_source == "HISTORICAL_RESEARCH" else "MANUAL_INPUT"),
        )
        new_balance = self.balance - trade.stake
        if self.repository is not None:
            self.repository.save_open_trade(trade, new_balance)
        self.balance = new_balance
        self.trades.append(trade)
        return trade

    def _find_open_trade(self, trade_id):
        trade = next((t for t in self.trades if t.trade_id == trade_id), None)
        if trade is None:
            raise ValueError("Trade not found.")
        if trade.status != "OPEN":
            raise ValueError("Trade has already been settled.")
        return trade

    def _complete_settlement(self, trade, exit_price, exit_time, price_source, expiry_price_time):
        old_balance = self.balance
        old_values = (
            trade.status, trade.exit_price, trade.exit_time, trade.result,
            trade.profit_loss, trade.price_source, trade.expiry_price_time,
        )
        try:
            trade.exit_price = float(exit_price)
            trade.exit_time = exit_time
            trade.price_source = price_source
            trade.expiry_price_time = expiry_price_time
            if trade.exit_price == trade.entry_price:
                trade.result = "PUSH"
                trade.profit_loss = 0.0
                new_balance = old_balance + trade.stake
            elif (
                (trade.direction == "UP" and trade.exit_price > trade.entry_price)
                or (trade.direction == "DOWN" and trade.exit_price < trade.entry_price)
            ):
                trade.result = "WIN"
                trade.profit_loss = trade.stake * trade.payout_rate
                new_balance = old_balance + trade.stake + trade.profit_loss
            else:
                trade.result = "LOSS"
                trade.profit_loss = -trade.stake
                new_balance = old_balance
            trade.status = "CLOSED"
            if self.repository is not None:
                self.repository.save_settled_trade(trade, new_balance)
            self.balance = new_balance
        except Exception:
            self.balance = old_balance
            (
                trade.status, trade.exit_price, trade.exit_time, trade.result,
                trade.profit_loss, trade.price_source, trade.expiry_price_time,
            ) = old_values
            raise
        return trade

    def settle_trade(
        self, trade_id, exit_price, exit_time,
        price_source="MANUAL_INPUT", expiry_price_time=None,
    ):
        trade = self._find_open_trade(trade_id)
        if trade.trade_source != "MANUAL_TEST":
            raise ValueError("Manual settlement is allowed only for MANUAL_TEST trades.")
        if not isfinite(float(exit_price)) or exit_price <= 0:
            raise ValueError("Exit price must be positive and finite.")
        if not isinstance(exit_time, datetime) or exit_time.tzinfo is None or exit_time.utcoffset() is None:
            raise ValueError("Exit time must be timezone-aware.")
        if price_source != "MANUAL_INPUT":
            raise ValueError("Manual settlement requires MANUAL_INPUT price source.")
        if expiry_price_time is not None:
            raise ValueError("Manual settlement cannot claim a verified expiry price.")
        exit_time = exit_time.astimezone(timezone.utc)
        if exit_time < trade.entry_time + timedelta(minutes=trade.expiry_minutes):
            raise ValueError("Trade expiry time has not been reached.")
        return self._complete_settlement(trade, exit_price, exit_time, "MANUAL_INPUT", None)

    def settle_historical_trade(self, trade_id, candles, retrieved_at):
        """Research-only settlement using a completed historical candle."""
        from simulator.candle_settlement import get_expiry_price

        trade = self._find_open_trade(trade_id)
        if trade.trade_source != "HISTORICAL_RESEARCH":
            raise ValueError("Historical settlement requires a HISTORICAL_RESEARCH trade.")
        expiry = get_expiry_price(
            candles=candles, entry_time=trade.entry_time,
            expiry_minutes=trade.expiry_minutes, retrieved_at=retrieved_at,
        )
        return self._complete_settlement(
            trade, expiry.price, expiry.expiry_time,
            "HISTORICAL_CANDLE", expiry.candle_time,
        )
