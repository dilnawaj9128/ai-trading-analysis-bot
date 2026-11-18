
from data.market_data import MarketDataService
from indicators import calculate_indicators
from patterns import detect_candlestick_patterns
from strategy import generate_signal, print_signal_report

from database.repository import PaperTradingRepository
from simulator import (
    PaperTradingSimulator,
    calculate_performance_metrics,
    print_performance_report,
)


def print_paper_performance():

    print("\n")
    print("=" * 55)
    print("STAGE 6 - PAPER TRADING PERFORMANCE")
    print("=" * 55)

    try:
        repository = PaperTradingRepository()

        simulator = PaperTradingSimulator(
            repository=repository
        )

        metrics = calculate_performance_metrics(
            simulator.trades,
            simulator.initial_balance,
        )

        print_performance_report(metrics)

        print(
            f"Available Paper Balance : "
            f"{simulator.balance:.2f}"
        )

        print("\nDatabase: SQLite")
        print("Execution Mode: PAPER ONLY")

    except Exception as error:
        print("PAPER TRADING ERROR:", error)


def main():

    print("=" * 55)
    print("AI MARKET ANALYSIS BOT")
    print("STAGE 6 - ANALYSIS & PAPER TRADING")
    print("=" * 55)

    try:

        service = MarketDataService()

        result = service.get_market_data(
            symbol="EUR/USD",
            interval="1min",
            outputsize=100
        )

        print("\nASSET:", result["asset"])
        print("TIMEFRAME:", result["timeframe"])
        print("SOURCE:", result["source"])
        print("DATA MODE:", result["data_mode"])
        print("RETRIEVED:", result["retrieved_at"])

        quality = result["quality"]

        print("\nDATA QUALITY")
        print("-" * 30)

        print("Status:", quality.status)
        print("Candles:", quality.total_candles)
        print("Missing:", quality.missing_candles)
        print("Duplicates:", quality.duplicate_candles)
        print("Invalid:", quality.invalid_candles)
        print("Last candle age:", quality.last_candle_age_seconds)

        for warning in quality.warnings:
            print("WARNING:", warning)

        print("\nLATEST OHLC DATA")
        print("-" * 55)

        if result["data"].empty:
            print("No completed candles available.")
            return

        print(result["data"].tail(10).to_string(index=False))

        if not quality.is_usable:
            print("\nSIGNAL: NO TRADE")
            print("REASON: Market data quality is not VALID.")
            print("Directional analysis has been blocked.")
            return

        # Technical indicators
        analysis_data = calculate_indicators(
            result["data"]
        )

        # Candlestick patterns
        pattern_data = detect_candlestick_patterns(
            analysis_data
        )

        print("\nLATEST CANDLESTICK PATTERNS")
        print("=" * 60)

        pattern_columns = [
            "timestamp",
            "Open",
            "High",
            "Low",
            "Close",
            "Pattern",
            "Pattern_Direction",
            "Pattern_Description",
        ]

        print(
            pattern_data[pattern_columns]
            .tail(10)
            .to_string(index=False)
        )

        # Technical indicator report
        columns = [
            "timestamp",
            "Close",
            "RSI_14",
            "EMA_20",
            "EMA_50",
            "MACD",
            "MACD_signal",
            "MACD_histogram",
            "ATR_14",
            "Volatility_20_pct",
            "Support",
            "Resistance",
        ]

        print("\nTECHNICAL INDICATORS")
        print("=" * 60)

        print(
            analysis_data[columns]
            .tail(10)
            .to_string(index=False)
        )

        # Analysis-only signal
        signal_result = generate_signal(
            pattern_data,
            expiry_minutes=15,
            data_mode=result["data_mode"],
            data_quality_status=quality.status,
        )

        print_signal_report(signal_result)

        print("\nSTAGE 6 - ANALYSIS ENGINE READY")

    except Exception as error:
        print("\nMARKET DATA / ANALYSIS ERROR:", error)

    finally:
        # Always display saved paper trading performance
        print_paper_performance()


if __name__ == "__main__":
    main()

