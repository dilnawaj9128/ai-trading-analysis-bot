"""Offline-only historical observation report analytics."""

import pandas as pd


def filter_historical_report(results, start_utc, end_utc):
    if not isinstance(results, pd.DataFrame):
        raise ValueError("Expected a DataFrame")

    required = {
        "observation_utc",
        "price_change",
        "historical_direction",
    }

    if not required.issubset(results.columns):
        raise ValueError("Missing report columns")

    start = pd.Timestamp(start_utc)
    end = pd.Timestamp(end_utc)

    if start.tzinfo is None or end.tzinfo is None:
        raise ValueError("Timezone-aware filter required")

    start = start.tz_convert("UTC")
    end = end.tz_convert("UTC")

    if start > end:
        raise ValueError("Start must not exceed end")

    timestamps = pd.to_datetime(
        results["observation_utc"],
        utc=True,
        errors="raise",
    )

    filtered = results.loc[
        timestamps.between(start, end)
    ].copy()

    return filtered.reset_index(drop=True)


def summarize_historical_report(results):
    if results.empty:
        return {
            "total": 0,
            "up": 0,
            "down": 0,
            "flat": 0,
            "average_change": None,
        }

    allowed = {"UP", "DOWN", "FLAT"}
    if not results["historical_direction"].isin(allowed).all():
        raise ValueError("Invalid historical direction")

    changes = pd.to_numeric(
        results["price_change"], errors="raise"
    )

    if not changes.map(
        lambda value: pd.notna(value) and abs(value) != float("inf")
    ).all():
        raise ValueError("Invalid price changes")

    counts = results["historical_direction"].value_counts()

    return {
        "total": len(results),
        "up": int(counts.get("UP", 0)),
        "down": int(counts.get("DOWN", 0)),
        "flat": int(counts.get("FLAT", 0)),
        "average_change": float(changes.mean()),
    }
