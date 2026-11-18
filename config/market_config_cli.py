
"""CLI for validating research-only market configurations."""

import argparse
import json

from config.market_config import (
    MARKETS,
    PLATFORMS,
    TIMEFRAMES,
    ResearchConfigError,
    create_research_config,
    research_disclaimer,
)


def main():
    parser = argparse.ArgumentParser(
        description="Multi-platform research configuration"
    )

    parser.add_argument(
        "--platform",
        required=True,
        choices=tuple(PLATFORMS),
    )
    parser.add_argument(
        "--market",
        required=True,
        choices=tuple(MARKETS),
    )
    parser.add_argument(
        "--symbol",
        required=True,
    )
    parser.add_argument(
        "--timeframe",
        default="1min",
        choices=tuple(TIMEFRAMES),
    )
    parser.add_argument(
        "--expiry",
        type=int,
        default=15,
    )

    args = parser.parse_args()

    try:
        config = create_research_config(
            platform=args.platform,
            market=args.market,
            symbol=args.symbol,
            timeframe=args.timeframe,
            expiry_minutes=args.expiry,
        )
    except ResearchConfigError as exc:
        parser.error(str(exc))

    print("\nMULTI-MARKET RESEARCH CONFIGURATION")
    print("=" * 50)
    print(json.dumps(config.to_dict(), indent=2))
    print("\n", research_disclaimer(config))
    print("Execution: ANALYSIS ONLY")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

