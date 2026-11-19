"""Stage 37: offline market-regime performance report."""

import argparse

from research.stage29_backtest import load_candles
from research.stage37_market_regime import run_regime_analysis


def print_table(title, rows):
    print(f"\n=== {title} ===")

    if not rows:
        print("No qualifying historical signals.")
        return

    print(
        f'{"Market regime":<20}'
        f'{"Wins":>7}'
        f'{"Losses":>9}'
        f'{"Push":>7}'
        f'{"Win Rate":>12}'
        f'{"Net":>10}'
    )

    print("-" * 65)

    for item in rows:
        rate = (
            f'{item["win_rate"]:.2%}'
            if item["win_rate"] is not None
            else "N/A"
        )

        print(
            f'{item["group"]:<20}'
            f'{item["wins"]:>7}'
            f'{item["losses"]:>9}'
            f'{item["pushes"]:>7}'
            f'{rate:>12}'
            f'{item["net_units"]:>10.2f}'
        )

        if item["evidence"] == "SMALL SAMPLE":
            print(
                f'  Warning: only {item["resolved"]} '
                'resolved trades; insufficient evidence'
            )


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--csv",
        default="data/historical/eurusd_1min_1day.csv",
    )

    parser.add_argument("--train", type=int, default=720)
    parser.add_argument("--test", type=int, default=180)
    parser.add_argument("--payout", type=float, default=0.80)
    args = parser.parse_args()

    candles = load_candles(args.csv)

    result = run_regime_analysis(
        candles,
        initial_train=args.train,
        test_size=args.test,
        payout=args.payout,
    )

    print("\n=== STAGE 37 MARKET REGIME ANALYSIS ===")
    print("Candles:", len(candles))
    print("Walk-forward trades:", result["total_trades"])
    print("Expiry: 15 minutes")
    print("API requests: 0")
    print("Execution: DISABLED")

    print_table(
        "TREND STRENGTH",
        result["by_trend"],
    )

    print_table(
        "VOLATILITY",
        result["by_volatility"],
    )

    print_table(
        "TREND + VOLATILITY",
        result["by_combined"],
    )

    summary = result["aggregate"]

    print("\n=== OVERALL RESULTS ===")
    print("Resolved:", summary["resolved"])
    print("Wins:", summary["wins"])
    print("Losses:", summary["losses"])
    print("Pushes:", summary["pushes"])
    print(
        "Win rate:",
        "N/A" if summary["win_rate"] is None
        else f'{summary["win_rate"]:.2%}',
    )
    print("Net units:", summary["net_units"])

    print("\nVERDICT: EXPLORATORY RESEARCH ONLY")
    print("Regime analysis does not prove a profitable edge.")
    print("Do not choose new filters using this test result.")
    print("Historical feed provenance remains unverified.")
    print("No API calls or real-money trading.")


if __name__ == "__main__":
    main()
