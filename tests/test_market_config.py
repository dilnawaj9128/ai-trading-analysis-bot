
import pytest

from config.market_config import (
    MARKETS,
    PLATFORMS,
    TIMEFRAMES,
    ResearchConfigError,
    create_research_config,
    research_disclaimer,
)


def test_quotex_eurusd():
    config = create_research_config(
        "quotex", "forex", "EUR/USD"
    )

    assert config.platform == "quotex"
    assert config.symbol == "EUR/USD"
    assert config.timeframe == "1min"
    assert config.expiry_minutes == 15


def test_olymp_trade_crypto():
    config = create_research_config(
        "olymp_trade",
        "crypto",
        "BTC/USD",
        "5min",
        15,
    )

    assert config.platform == "olymp_trade"
    assert config.market == "crypto"
    assert config.timeframe == "5min"


def test_all_configured_symbols():
    for platform in PLATFORMS:
        for market, symbols in MARKETS.items():
            for symbol in symbols:
                for timeframe in TIMEFRAMES:
                    config = create_research_config(
                        platform,
                        market,
                        symbol,
                        timeframe,
                        15,
                    )

                    assert config.symbol == symbol
                    assert config.analysis_only is True
                    assert config.execution_enabled is False


def test_reject_unknown_platform():
    with pytest.raises(ResearchConfigError):
        create_research_config(
            "unknown", "forex", "EUR/USD"
        )


def test_reject_unknown_market():
    with pytest.raises(ResearchConfigError):
        create_research_config(
            "quotex", "unknown", "EUR/USD"
        )


def test_reject_wrong_market_symbol():
    with pytest.raises(ResearchConfigError):
        create_research_config(
            "quotex", "crypto", "EUR/USD"
        )


def test_reject_otc_symbol():
    with pytest.raises(ResearchConfigError):
        create_research_config(
            "quotex", "forex", "EUR/USD OTC"
        )


def test_reject_unsupported_timeframe():
    with pytest.raises(ResearchConfigError):
        create_research_config(
            "quotex",
            "forex",
            "EUR/USD",
            "30min",
        )


def test_reject_unsupported_expiry():
    for invalid in (1, 5, 30, True, "15"):
        with pytest.raises(ResearchConfigError):
            create_research_config(
                "quotex",
                "forex",
                "EUR/USD",
                expiry_minutes=invalid,
            )


def test_safety_flags_and_disclaimer():
    config = create_research_config(
        "olymp_trade",
        "forex",
        "GBP/USD",
    )

    payload = config.to_dict()

    assert payload["analysis_only"] is True
    assert payload["execution_enabled"] is False
    assert payload["broker_feed_verified"] is False
    assert payload["provider_feed_verified"] is False
    assert (
        payload["directional_backtesting_allowed"]
        is False
    )

    disclaimer = research_disclaimer(config)

    assert "Olymp Trade" in disclaimer
    assert "No OTC support" in disclaimer

