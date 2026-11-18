"""Pure, offline research calculations from already audited completed candles."""

import pandas as pd

from analysis.live_engine import analyze_live_candles
from analysis.smart_market import assess_market


def build_advanced_research(frame: pd.DataFrame) -> dict:
    """Describe past candles without a directional trade signal or network calls.

    Caller must verify the CSV/receipt and completed-candle timestamps first.
    """
    if not isinstance(frame, pd.DataFrame):
        raise TypeError("Expected historical candle DataFrame")
    if len(frame) < 60:
        raise ValueError("At least 60 completed candles required")

    analysis = analyze_live_candles(frame.copy(deep=True))
    enriched = analysis["frame"]
    patterns = analysis["patterns"]
    if not enriched.index.equals(patterns.index):
        raise ValueError("Pattern and indicator rows do not align")

    # Historical data is not stale merely because it is old; validated
    # contiguous source candles are required by the caller's dataset audit.
    assessment = assess_market(analysis, stale=False, gaps=0)
    return {
        "enriched": enriched,
        "patterns": patterns,
        "latest": analysis["latest"],
        "observations": analysis["observations"],
        "assessment": assessment,
        "action": "NO TRADE",
        "analysis_only": True,
        "execution_enabled": False,
        "directional_backtesting_allowed": False,
    }
