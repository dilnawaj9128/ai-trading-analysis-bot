
from dataclasses import dataclass
from datetime import datetime


@dataclass
class PaperAccount:
    initial_balance: float
    balance: float


@dataclass
class StoredTrade:
    trade_id: str
    direction: str
    entry_price: float
    stake: float
    payout_rate: float
    expiry_minutes: int
    entry_time: datetime
    status: str
    exit_price: float | None = None
    exit_time: datetime | None = None
    result: str | None = None
    profit_loss: float = 0.0

    trade_source: str = "MANUAL_TEST"
    price_source: str = "MANUAL_INPUT"
    expiry_price_time: datetime | None = None

