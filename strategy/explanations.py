
def print_signal_report(result):
    print("\nMARKET SIGNAL ANALYSIS")
    print("=" * 55)
    print("SIGNAL:", result["signal"])
    print("TREND:", result.get("trend", "UNKNOWN"))
    print("MOMENTUM:", result.get("momentum", "UNKNOWN"))
    print("VOLATILITY:", result.get("volatility", "UNKNOWN"))

    if result.get("atr_percent") is not None:
        print(f"ATR (%): {result['atr_percent']:.5f}")

    if result.get("expiry_minutes") is not None:
        print("ANALYSIS EXPIRY:", result["expiry_minutes"], "minutes")

    print("\nREASONS:")
    for reason in result["reasons"]:
        print("-", reason)

    print("\nAnalysis only. No automatic trade execution.")

