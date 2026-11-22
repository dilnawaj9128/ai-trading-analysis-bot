"""Read-only research adapter for stored OHLC candles."""

import pandas as pd

from analysis.live_engine import analyze_live_candles
from market_data.providers.data_quality_gate import validate_live_frame
from market_data.providers.candle_repository import CandleRepository


def load_candle_frame(
    db_path,
    *,
    source="SIMULATED",
    symbol="EURUSD_otc",
    limit=500,
):
    if type(limit) is not int or limit < 60:
        raise ValueError("At least 60 candles required")

    repo = CandleRepository(db_path)

    with repo._connect() as conn:
        rows = conn.execute(
            """
            SELECT timestamp, open, high, low, close
            FROM candles
            WHERE source = ? AND symbol = ?
              AND timeframe = '1min'
            ORDER BY timestamp DESC
            LIMIT ?
            """,
            (source, symbol, limit),
        ).fetchall()

    if len(rows) < 60:
        raise ValueError("Insufficient completed candles")

    frame = pd.DataFrame(
        reversed(rows),
        columns=["timestamp", "Open", "High", "Low", "Close"],
    )

    frame["timestamp"] = pd.to_datetime(
        frame["timestamp"], utc=True
    )

    if frame["timestamp"].duplicated().any():
        raise ValueError("Duplicate timestamps")

    if not frame["timestamp"].is_monotonic_increasing:
        raise ValueError("Unsorted timestamps")

    if (
        frame["timestamp"].diff().dropna()
        != pd.Timedelta(minutes=1)
    ).any():
        raise ValueError("Missing candle intervals")

    return frame


def analyze_stored_candles(
    db_path,
    *,
    source="SIMULATED",
    symbol="EURUSD_otc",
    now=None,
):
    frame = load_candle_frame(
        db_path, source=source, symbol=symbol
    )

    quality = validate_live_frame(frame, now=now)
    result = analyze_live_candles(quality["frame"])

    return {
        "status": "RESEARCH_ONLY",
        "source": source,
        "symbol": symbol,
        "candles": quality["candles"],
        "age_seconds": quality["age_seconds"],
        "data_quality": quality["quality"],
        "observations": result["observations"],
        "signal": "NO TRADE",
        "feed_verified": False,
        "analysis_only": True,
        "execution_enabled": False,
    }
