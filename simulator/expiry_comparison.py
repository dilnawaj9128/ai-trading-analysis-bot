
"""Stage 6.6.2 - Compare 1m, 5m and 15m backtests.

All results are isolated research simulations.
"""

from dataclasses import dataclass
from datetime import timedelta

from data.historical_csv import load_historical_csv
from simulator.backtesting import run_backtest
from simulator.historical_integrity import (
    HistoricalProvenance,
    validate_provenance,
)


EXPIRIES = (1, 5, 15)


@dataclass(frozen=True)
class ExpiryComparison:
    dataset: object
    provenance: HistoricalProvenance
    reports: dict


def compare_expiries(
    csv_path,
    provenance,
    *,
    stake=50.0,
    payout_rate=0.80,
    warmup_candles=50,
):
    """Run the same historical strategy for each expiry."""

    if not isinstance(
        provenance, HistoricalProvenance
    ):
        raise ValueError(
            "HistoricalProvenance is required."
        )

    # Validate metadata, but do not claim that this
    # independently authenticates the data provider.
    validate_provenance(provenance)

    mode = str(provenance.feed_mode).strip().lower()

    if mode not in {"live", "delayed"}:
        raise ValueError(
            "Comparison requires a verified live "
            "or delayed feed mode."
        )

    if warmup_candles < 50:
        raise ValueError(
            "At least 50 warmup candles required."
        )

    dataset = load_historical_csv(
        csv_path,
        min_candles=warmup_candles + max(EXPIRIES) + 1,
    )

    # Require the stated retrieval time to be after
    # the entire CSV dataset's final candle completes.
    # This is a consistency check, not proof that
    # the provider metadata is authentic.
    last_candle_end = (
        dataset.end_time + timedelta(minutes=1)
    )

    if provenance.retrieved_at < last_candle_end:
        raise ValueError(
            "retrieved_at precedes dataset completion."
        )

    reports = {}

    for expiry in EXPIRIES:
        reports[expiry] = run_backtest(
            dataset.candles,
            provenance,
            expiry_minutes=expiry,
            stake=stake,
            payout_rate=payout_rate,
            warmup_candles=warmup_candles,
        )

    return ExpiryComparison(
        dataset=dataset,
        provenance=provenance,
        reports=reports,
    )


def print_expiry_comparison(comparison):
    dataset = comparison.dataset

    print("\n" + "=" * 78)
    print("STAGE 6.6.2 - HISTORICAL EXPIRY COMPARISON")
    print("=" * 78)

    print("Execution : ANALYSIS ONLY")
    print("Broker verification: NONE")
    print("Dataset   :", dataset.file_path)
    print("Candles   :", dataset.candle_count)
    print("Start UTC :", dataset.start_time)
    print("End UTC   :", dataset.end_time)

    print(
        "Provider claim:",
        comparison.provenance.provider
    )
    print(
        "Feed mode claim:",
        comparison.provenance.feed_mode
    )

    print("-" * 78)

    print(
        f"{'Expiry':<10}"
        f"{'Signals':>9}"
        f"{'Trades':>9}"
        f"{'Wins':>7}"
        f"{'Losses':>8}"
        f"{'Pushes':>8}"
        f"{'Win %':>9}"
        f"{'P&L':>10}"
    )

    print("-" * 78)

    for expiry in EXPIRIES:
        report = comparison.reports[expiry]

        print(
            f"{str(expiry) + 'm':<10}"
            f"{report.signals_checked:>9}"
            f"{len(report.trades):>9}"
            f"{report.wins:>7}"
            f"{report.losses:>8}"
            f"{report.pushes:>8}"
            f"{report.win_rate:>9.2f}"
            f"{report.total_pnl:>10.2f}"
        )

    print("-" * 78)

    print("\nMAX DRAWDOWN BY EXPIRY")

    for expiry in EXPIRIES:
        report = comparison.reports[expiry]
        print(
            f"{expiry:>2}m: "
            f"{report.max_drawdown:.2f}"
        )

    print("\nNOTES:")
    print("- Synthetic or unverified feeds do not prove accuracy.")
    print("- Each expiry runs as an independent simulation.")
    print("- No SQLite paper account balance is modified.")
    print("- No automatic trading or broker execution.")
    print("=" * 78)

