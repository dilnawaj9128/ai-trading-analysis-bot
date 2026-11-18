"""Offline historical strategy evaluation with strict provenance gates."""

import pandas as pd

from indicators import calculate_indicators
from patterns.candlestick import detect_candlestick_patterns
from strategy.signal_engine import generate_signal
from analysis.historical_observation import (
    evaluate_historical_window,
)


def compare_directions(signal, outcome):
    if signal == "NO TRADE":
        return "NOT_EVALUATED"

    if signal not in ("UP", "DOWN"):
        raise ValueError("Unsupported strategy signal")

    if outcome not in ("UP", "DOWN", "FLAT"):
        raise ValueError("Unsupported historical outcome")

    if outcome == "FLAT":
        return "FLAT_OUTCOME"

    return "MATCH" if signal == outcome else "MISMATCH"


def evaluate_historical_signal(
    frame: pd.DataFrame,
    *,
    selected_index: int,
):
    """Use only selected-and-earlier candles for signal generation."""

    observation = evaluate_historical_window(
        frame,
        selected_index=selected_index,
        expiry_minutes=15,
    )

    past = observation["indicator_input"].copy()

    if len(past) < 60:
        raise ValueError("At least 60 historical candles required")

    enriched = calculate_indicators(past)
    patterns = detect_candlestick_patterns(past)

    enriched["Pattern_Direction"] = (
        patterns["Pattern_Direction"].to_numpy()
    )

    # Fail closed: offline dataset feed provenance is not verified.
    signal_result = generate_signal(
        enriched,
        expiry_minutes=15,
        data_mode="unknown",
        data_quality_status="INVALID",
    )

    signal = signal_result["signal"]
    outcome = observation["historical_direction"]

    return {
        "observation_utc": observation["observation_close_utc"],
        "evaluation_utc": observation["evaluation_close_utc"],
        "signal": signal,
        "historical_outcome": outcome,
        "comparison": compare_directions(signal, outcome),
        "reasons": signal_result["reasons"],
        "expiry_minutes": 15,
        "candles_used_for_signal": len(past),
        "analysis_only": True,
        "feed_verified": False,
        "execution_enabled": False,
        "prediction_accuracy_available": False,
    }
