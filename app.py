
from data.market_data import MarketDataService


def main():

    print("=" * 55)
    print("AI MARKET ANALYSIS BOT")
    print("STAGE 2 - MARKET DATA INTEGRATION")
    print("=" * 55)

    service = MarketDataService()

    try:

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
        print(
            "Last candle age:",
            quality.last_candle_age_seconds
        )

        for warning in quality.warnings:
            print("WARNING:", warning)

        print("\nLATEST OHLC DATA")
        print("-" * 55)

        if result["data"].empty:
            print("No completed candles available.")
        else:
            print(result["data"].tail(10).to_string(index=False))

        if quality.is_usable:
            print("\nDATA READY FOR TECHNICAL ANALYSIS")
        else:
            print("\nDATA NOT SUITABLE FOR SIGNAL GENERATION")

    except Exception as error:

        print("\nMARKET DATA ERROR:", error)


if __name__ == "__main__":
    main()

