from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path

import pandas as pd

from data.dataset_quality import audit_dataset


CSV_NAME = "eurusd_1min_utc.csv"
RECEIPT_NAME = "acquisition.json"
PRICE_COLUMNS = ("Open", "High", "Low", "Close")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_frame(csv_path: Path) -> pd.DataFrame:
    frame = pd.read_csv(csv_path)
    frame["timestamp"] = pd.to_datetime(
        frame["timestamp"], utc=True
    )
    return frame.sort_values("timestamp").reset_index(drop=True)


def analyze_session(dataset_dir: str | Path) -> dict:
    """Analyze one dataset without trading or predictions."""

    base = Path(dataset_dir)
    csv_path = base / CSV_NAME
    receipt_path = base / RECEIPT_NAME

    audit = audit_dataset(csv_path, receipt_path)

    result = {
        "dataset": str(base),
        "status": audit["status"],
        "quality": {
            "structural_integrity": audit["structural_integrity"],
            "errors": audit["errors"],
            "warnings": audit["warnings"],
        },
        "directional_backtesting_allowed": False,
        "statistics": None,
    }

    if (
        audit["status"] != "PASS"
        or not audit["structural_integrity"]
    ):
        return result

    frame = _load_frame(csv_path)

    opens = frame["Open"].astype(float)
    highs = frame["High"].astype(float)
    lows = frame["Low"].astype(float)
    closes = frame["Close"].astype(float)

    ranges = highs - lows
    bodies = (closes - opens).abs()
    returns = closes.pct_change().dropna()

    result["statistics"] = {
        "candle_count": int(len(frame)),
        "start": frame["timestamp"].iloc[0].isoformat(),
        "end": frame["timestamp"].iloc[-1].isoformat(),
        "first_open": float(opens.iloc[0]),
        "last_close": float(closes.iloc[-1]),
        "net_change": float(
            closes.iloc[-1] - opens.iloc[0]
        ),
        "net_change_percent": float(
            (closes.iloc[-1] / opens.iloc[0] - 1) * 100
        ),
        "bullish_candles": int((closes > opens).sum()),
        "bearish_candles": int((closes < opens).sum()),
        "doji_candles": int((closes == opens).sum()),
        "average_range": float(ranges.mean()),
        "maximum_range": float(ranges.max()),
        "average_body": float(bodies.mean()),
        "close_return_std": (
            float(returns.std(ddof=0))
            if len(returns) else 0.0
        ),
    }

    result["source"] = {
        "csv_sha256": _sha256(csv_path),
        "receipt_sha256": _sha256(receipt_path),
    }

    return result


def _session_candles(dataset_dir: str | Path) -> dict:
    """Map UTC candle timestamps to OHLC tuples."""

    frame = _load_frame(Path(dataset_dir) / CSV_NAME)

    return {
        row.timestamp: tuple(
            float(getattr(row, column))
            for column in PRICE_COLUMNS
        )
        for row in frame.itertuples(index=False)
    }


def analyze_multiple_sessions(
    dataset_dirs: list[str | Path],
) -> dict:
    """Compare datasets and count only accepted unique candles."""

    if not dataset_dirs:
        raise ValueError(
            "At least one dataset directory is required"
        )

    sessions = []
    accepted = []

    seen_paths = {}
    seen_hashes = {}
    occupied_candles = {}

    duplicates = []
    overlaps = []

    for dataset_dir in dataset_dirs:
        session = analyze_session(dataset_dir)

        # Preserve the original session status for compatibility.
        session["selection_status"] = "EXCLUDED"
        session["selection_reason"] = None

        sessions.append(session)
        index = len(sessions)

        if session["status"] != "PASS":
            session["selection_reason"] = "QUALITY_FAILED"
            continue

        canonical_path = str(
            Path(dataset_dir).resolve()
        )
        csv_hash = session["source"]["csv_sha256"]

        if canonical_path in seen_paths:
            original = seen_paths[canonical_path]

            session["selection_status"] = "DUPLICATE"
            session["selection_reason"] = "SAME_DIRECTORY"
            session["duplicate_of"] = original

            duplicates.append({
                "session": index,
                "duplicate_of": original,
                "reason": "SAME_DIRECTORY",
            })
            continue

        if csv_hash in seen_hashes:
            original = seen_hashes[csv_hash]

            session["selection_status"] = "DUPLICATE"
            session["selection_reason"] = "IDENTICAL_CSV"
            session["duplicate_of"] = original

            duplicates.append({
                "session": index,
                "duplicate_of": original,
                "reason": "IDENTICAL_CSV",
            })
            continue

        candles = _session_candles(dataset_dir)

        repeated = set(candles).intersection(
            occupied_candles
        )

        if repeated:
            conflicting = sum(
                candles[timestamp] != occupied_candles[timestamp]
                for timestamp in repeated
            )

            session["selection_status"] = "OVERLAP"
            session["selection_reason"] = (
                "CONFLICTING_PRICES"
                if conflicting
                else "REPEATED_TIMESTAMPS"
            )

            session["overlap_count"] = len(repeated)
            session["conflicting_candle_count"] = conflicting

            overlaps.append({
                "session": index,
                "overlap_count": len(repeated),
                "conflicting_candle_count": conflicting,
                "first_overlap": min(repeated).isoformat(),
                "last_overlap": max(repeated).isoformat(),
            })
            continue

        # Only accepted sessions contribute to future comparisons.
        session["selection_status"] = "ACCEPTED"
        session["selection_reason"] = None

        accepted.append(session)

        seen_paths[canonical_path] = index
        seen_hashes[csv_hash] = index
        occupied_candles.update(candles)

    total_candles = sum(
        item["statistics"]["candle_count"]
        for item in accepted
    )

    bullish = sum(
        item["statistics"]["bullish_candles"]
        for item in accepted
    )
    bearish = sum(
        item["statistics"]["bearish_candles"]
        for item in accepted
    )
    doji = sum(
        item["statistics"]["doji_candles"]
        for item in accepted
    )

    total_range = sum(
        item["statistics"]["average_range"]
        * item["statistics"]["candle_count"]
        for item in accepted
    )

    combined_statistics = {
        "candle_count": total_candles,
        "bullish_candles": bullish,
        "bearish_candles": bearish,
        "doji_candles": doji,
        "average_range": (
            total_range / total_candles
            if total_candles else None
        ),
        "first_timestamp": (
            min(occupied_candles).isoformat()
            if occupied_candles else None
        ),
        "last_timestamp": (
            max(occupied_candles).isoformat()
            if occupied_candles else None
        ),
    }

    return {
        "schema_version": 2,
        "report_type": "multi_session_historical_research",
        "analysis_only": True,
        "directional_backtesting_allowed": False,
        "datasets_requested": len(sessions),
        "datasets_passed": sum(
            item["status"] == "PASS"
            for item in sessions
        ),
        "datasets_failed": sum(
            item["status"] != "PASS"
            for item in sessions
        ),
        "datasets_accepted": len(accepted),
        "datasets_duplicate": len(duplicates),
        "datasets_overlapping": len(overlaps),
        "total_valid_candles": total_candles,
        "combined_statistics": combined_statistics,
        "duplicates": duplicates,
        "overlaps": overlaps,
        "sessions": sessions,
        "limitations": [
            "Structural integrity does not prove feed authenticity",
            "Twelve Data prices are not verified Quotex execution prices",
            "Overlapping sessions are excluded, not merged",
            "Combined statistics are descriptive, not predictions",
            "Directional backtesting remains blocked",
        ],
    }


def export_research_report(
    report: dict,
    output_path: str | Path,
) -> Path:
    """Atomically export a research-only report."""

    output = Path(output_path)

    if (
        report.get("analysis_only") is not True
        or report.get(
            "directional_backtesting_allowed"
        ) is not False
    ):
        raise ValueError(
            "Research-only safety policy violation"
        )

    source_paths = set()

    for session in report.get("sessions", []):
        base = Path(session["dataset"])
        source_paths.add(
            (base / CSV_NAME).resolve()
        )
        source_paths.add(
            (base / RECEIPT_NAME).resolve()
        )

    if output.resolve() in source_paths:
        raise ValueError(
            "Cannot overwrite a source dataset"
        )

    output.parent.mkdir(
        parents=True, exist_ok=True
    )

    temporary = None

    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=output.parent,
            prefix=".research_",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary = Path(handle.name)

            json.dump(
                report,
                handle,
                indent=2,
                allow_nan=False,
            )
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())

        os.replace(temporary, output)

    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)

    return output
