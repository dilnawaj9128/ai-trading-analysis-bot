
"""Stage 7.1: research-only multi-market configuration."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Final


class ResearchConfigError(ValueError):
    """Invalid or unsupported research configuration."""


PLATFORMS: Final = {
    "quotex": {
        "label": "Quotex",
        "mode": "external_research",
    },
    "olymp_trade": {
        "label": "Olymp Trade",
        "mode": "external_research",
    },
}

MARKETS: Final = {
    "forex": ("EUR/USD", "GBP/USD", "USD/JPY"),
    "crypto": ("BTC/USD", "ETH/USD"),
    "stocks": ("AAPL", "TSLA", "NVDA"),
    "etfs": ("SPY", "QQQ"),
    "commodities": ("XAU/USD", "XAG/USD"),
}

TIMEFRAMES: Final = {
    "1min": 1,
    "5min": 5,
    "15min": 15,
}

EXPIRY_MINUTES: Final = (15,)


@dataclass(frozen=True)
class ResearchConfig:
    platform: str
    market: str
    symbol: str
    timeframe: str
    expiry_minutes: int

    provider: str = "twelve_data"
    analysis_only: bool = True
    execution_enabled: bool = False
    broker_feed_verified: bool = False
    provider_feed_verified: bool = False
    directional_backtesting_allowed: bool = False

    def to_dict(self):
        return asdict(self)


def create_research_config(
    platform: str,
    market: str,
    symbol: str,
    timeframe: str = "1min",
    expiry_minutes: int = 15,
) -> ResearchConfig:
    """
    Validate a research profile.

    No credentials, orders, signals or broker connectivity.
    """

    if platform not in PLATFORMS:
        raise ResearchConfigError(
            f"Unsupported platform: {platform}"
        )

    if market not in MARKETS:
        raise ResearchConfigError(
            f"Unsupported market: {market}"
        )

    if symbol not in MARKETS[market]:
        raise ResearchConfigError(
            f"{symbol} is not configured for {market}"
        )

    if timeframe not in TIMEFRAMES:
        raise ResearchConfigError(
            f"Unsupported timeframe: {timeframe}"
        )

    if (
        type(expiry_minutes) is not int
        or expiry_minutes not in EXPIRY_MINUTES
    ):
        raise ResearchConfigError(
            "Only 15-minute research expiry is supported"
        )

    return ResearchConfig(
        platform=platform,
        market=market,
        symbol=symbol,
        timeframe=timeframe,
        expiry_minutes=expiry_minutes,
    )


def research_disclaimer(config: ResearchConfig) -> str:
    label = PLATFORMS[config.platform]["label"]

    return (
        f"{label} external research only. "
        "Twelve Data and broker quotes may differ. "
        "No OTC support, verified broker feed, "
        "trade execution, directional backtesting "
        "or profitability claims."
    )

