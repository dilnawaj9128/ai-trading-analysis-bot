"""Offline batch report for historical 15-minute observations."""

import pandas as pd

from analysis.historical_observation import (
    evaluate_historical_window,
)


def build_historical_report(
    frame,
    *,
    start_index=59,
    step=15,
):
    if type(start_index) is not int or start_index < 0:
        raise ValueError("Invalid start index")

    if type(step) is not int or step < 15:
        raise ValueError(
            "Step must be at least 15 minutes to avoid overlapping outcomes"
        )

    if not isinstance(frame, pd.DataFrame):
        raise ValueError("Expected DataFrame")

    rows = []

    for index in range(start_index, len(frame) - 15, step):
        observation = evaluate_historical_window(
            frame,
            selected_index=index,
            expiry_minutes=15,
        )

        rows.append({
            "observation_utc": observation["observation_close_utc"],
            "evaluation_utc": observation["evaluation_close_utc"],
            "entry_close": observation["entry_close"],
            "exit_close": observation["exit_close"],
            "price_change": observation["price_change"],
            "historical_direction": observation["historical_direction"],
            "expiry_minutes": 15,
        })

    if not rows:
        raise ValueError(
            "Insufficient historical data for batch evaluation"
        )

    results = pd.DataFrame(rows)

    counts = results["historical_direction"].value_counts()

    summary = {
        "total_observations": len(results),
        "up": int(counts.get("UP", 0)),
        "down": int(counts.get("DOWN", 0)),
        "flat": int(counts.get("FLAT", 0)),
        "average_price_change": float(
            results["price_change"].mean()
        ),
        "analysis_only": True,
        "prediction_accuracy_available": False,
    }

    return {
        "results": results,
        "summary": summary,
    }
