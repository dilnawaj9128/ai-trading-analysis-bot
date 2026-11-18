
"""Export isolated backtesting research reports."""

import csv
import json
from datetime import datetime, timezone
from pathlib import Path


def _utc_string(value):
    return value.isoformat()


def export_backtest_reports(
    comparison,
    verified,
    output_dir,
):
    output_dir = Path(output_dir)
    output_dir.mkdir(
        parents=True, exist_ok=True
    )

    # Fixed filenames inside a user-selected directory.
    summary_path = output_dir / "summary.json"
    comparison_path = output_dir / "comparison.csv"
    trades_path = output_dir / "trades.csv"

    rows = []
    trade_rows = []

    for expiry in sorted(comparison.reports):
        report = comparison.reports[expiry]

        rows.append({
            "expiry_minutes": expiry,
            "signals_checked": report.signals_checked,
            "no_trade_count": report.no_trade_count,
            "trades": len(report.trades),
            "wins": report.wins,
            "losses": report.losses,
            "pushes": report.pushes,
            "win_rate_percent": report.win_rate,
            "total_pnl": report.total_pnl,
            "max_drawdown": report.max_drawdown,
        })

        for trade in report.trades:
            trade_rows.append({
                "expiry_minutes": expiry,
                "direction": trade.direction,
                "entry_time": _utc_string(
                    trade.entry_time
                ),
                "expiry_time": _utc_string(
                    trade.expiry_time
                ),
                "entry_price": trade.entry_price,
                "expiry_price": trade.expiry_price,
                "result": trade.result,
                "profit_loss": trade.profit_loss,
            })

    summary = {
        "schema_version": 1,
        "research_only": True,
        "broker_verified": False,
        "generated_at": datetime.now(
            timezone.utc
        ).isoformat(),
        "dataset": {
            "path": str(
                comparison.dataset.file_path
            ),
            "candles": comparison.dataset.candle_count,
            "start_time": _utc_string(
                comparison.dataset.start_time
            ),
            "end_time": _utc_string(
                comparison.dataset.end_time
            ),
            "sha256": verified.dataset_sha256,
        },
        "provenance": {
            "provider": verified.provenance.provider,
            "feed_mode": verified.provenance.feed_mode,
            "retrieved_at": _utc_string(
                verified.provenance.retrieved_at
            ),
            "manifest_sha256": verified.manifest_sha256,
            "verification_reference": (
                verified.trust_reference
            ),
            "trust_model": "local_allowlist",
        },
        "comparison": rows,
        "notes": [
            "Historical research only.",
            "Not verified against Quotex prices.",
            "Idealized entry and expiry prices.",
            "Local trust registry does not independently authenticate provider data.",
            "Paper trading SQLite database unchanged.",
        ],
    }

    with summary_path.open(
        "w", encoding="utf-8"
    ) as stream:
        json.dump(
            summary, stream,
            indent=2,
            allow_nan=False,
        )

    def write_csv(path, fieldnames, records):
        with path.open(
            "w", newline="", encoding="utf-8"
        ) as stream:
            writer = csv.DictWriter(
                stream,
                fieldnames=fieldnames,
            )
            writer.writeheader()
            writer.writerows(records)

    write_csv(
        comparison_path,
        [
            "expiry_minutes",
            "signals_checked",
            "no_trade_count",
            "trades",
            "wins",
            "losses",
            "pushes",
            "win_rate_percent",
            "total_pnl",
            "max_drawdown",
        ],
        rows,
    )

    write_csv(
        trades_path,
        [
            "expiry_minutes",
            "direction",
            "entry_time",
            "expiry_time",
            "entry_price",
            "expiry_price",
            "result",
            "profit_loss",
        ],
        trade_rows,
    )

    return {
        "summary": summary_path,
        "comparison": comparison_path,
        "trades": trades_path,
    }

