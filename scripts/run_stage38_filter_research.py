"""Stage 38 training-only accuracy research CLI."""

import argparse

from research.stage29_backtest import load_candles
from research.stage38_conservative_filters import (
    run_training_research,
)


def main():
    p = argparse.ArgumentParser()
    p.add_argument(
        "--csv",
        default="data/historical/eurusd_1min_1day.csv",
    )
    p.add_argument("--train", type=int, default=720)
    p.add_argument("--payout", type=float, default=0.80)
    args = p.parse_args()

    candles = load_candles(args.csv)

    result = run_training_research(
        candles,
        train_end=args.train,
        payout=args.payout,
    )

    print("\n=== STAGE 38 CONSERVATIVE FILTER RESEARCH ===")
    print("Historical candles:", len(candles))
    print("Training candles:", result["training_candles"])
    print("Future candles used for selection: 0")
    print("API requests: 0")
    print("Execution: DISABLED")

    print(
        f'\n{"Candidate":<22}'
        f'{"Resolved":>10}'
        f'{"Win Rate":>12}'
        f'{"Net Units":>12}'
    )
    print("-" * 56)

    for name, stats in result["candidates"].items():
        rate = (
            f'{stats["win_rate"]:.2%}'
            if stats["win_rate"] is not None
            else "N/A"
        )

        print(
            f'{name:<22}'
            f'{stats["resolved"]:>10}'
            f'{rate:>12}'
            f'{stats["net_units"]:>12.2f}'
        )

    print("\nProvisional:", result["provisional"])
    print(
        "Future research candidate:",
        result["selected_for_future_research"],
    )
    print("Decision:", result["decision"])

    print("\nCAUTION:")
    print("Dataset and regime ideas have already been inspected.")
    print("This is exploratory training research, not new proof.")
    print("Provider and broker parity are unverified.")
    print("Real-money trading is disabled.")


if __name__ == "__main__":
    main()
