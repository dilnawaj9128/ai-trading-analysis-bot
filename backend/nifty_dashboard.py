"""Read the existing NIFTY 50 monitor's local outputs for Market Lens."""

import sqlite3
from contextlib import closing
from datetime import datetime, time, timezone
from math import isfinite
from zoneinfo import ZoneInfo

import pandas as pd

from analysis.live_engine import analyze_live_candles
from dashboard.real_data_mode import validate_ohlc

IST = ZoneInfo("Asia/Kolkata")
ONE_MINUTE = pd.Timedelta(minutes=1)
HORIZONS = (5, 10, 15)
OHLC = ("Open", "High", "Low", "Close")
INDICATORS = ("RSI_14", "EMA_20", "EMA_50", "MACD", "ATR_14",
              "Support", "Resistance")
CANDLE_LIMIT = 120
OUTCOMES = ("WIN", "LOSS", "PUSH", "PENDING")
DIRECTIONS = ("UP", "DOWN")


def read_candles(path, now):
    if not path.is_file():
        return "WAITING FOR DATA", [], [], {}

    try:
        frame, quality = validate_ohlc(pd.read_csv(path), now=now, min_rows=1)
    except (OSError, ValueError, TypeError, KeyError, OverflowError):
        return "INVALID CANDLE DATA", [], [], {}

    candles = [
        [row.timestamp.isoformat(), *(float(getattr(row, name)) for name in OHLC)]
        for row in frame.tail(CANDLE_LIMIT).itertuples(index=False)
    ]
    candle_analysis = []
    if len(frame) >= 60 and not quality["gaps"]:
        result = analyze_live_candles(frame)
        values = result["frame"].loc[:, list(INDICATORS)].tail(CANDLE_LIMIT)
        patterns = result["patterns"]["Pattern"].tail(CANDLE_LIMIT)
        candle_analysis = [
            {
                "indicators": {
                    name: float(value)
                    for name, value in zip(INDICATORS, row)
                    if pd.notna(value) and isfinite(value)
                },
                "pattern": pattern if isinstance(pattern, str) else None,
            }
            for row, pattern in zip(values.itertuples(index=False, name=None), patterns)
        ]

    local = now.astimezone(IST)
    in_session = local.weekday() < 5 and time(9, 15) <= local.time() < time(15, 30)
    if not in_session:
        state = "MARKET CLOSED"
    elif quality["gaps"]:
        state = "CANDLE GAPS"
    elif quality["age_seconds"] > 120:
        state = "STALE DATA"
    else:
        state = "LIVE DATA"

    return state, candles, candle_analysis, quality


def research_record(row, now):
    try:
        opened, expiry = (pd.Timestamp(row[key]) for key in ("timestamp", "expiry"))
        if pd.isna(opened) or pd.isna(expiry) or opened.tzinfo is None or expiry.tzinfo is None:
            return None
        entry_time = opened + ONE_MINUTE
        expiry_time = expiry + ONE_MINUTE
        if entry_time > now or expiry_time - entry_time != pd.Timedelta(minutes=row["horizon"]):
            return None
        score = float(row["up_score"])
        if row["direction"] not in DIRECTIONS or row["result"] not in OUTCOMES or not 0 <= score <= 1:
            return None
        return {
            "time": entry_time.isoformat(),
            "expiry": expiry_time.isoformat(),
            "direction": row["direction"],
            "up_score": score,
            "result": row["result"],
        }
    except (ValueError, TypeError, OverflowError):
        return None


def read_predictions(path, now):
    if not path.is_file():
        return None

    try:
        with closing(sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True, timeout=2)) as db:
            db.row_factory = sqlite3.Row
            db.execute("BEGIN")
            counts = db.execute(
                """SELECT horizon, result, COUNT(*) AS count FROM predictions
                   GROUP BY horizon, result"""
            ).fetchall()
            history = {
                h: db.execute(
                    """SELECT timestamp, horizon, expiry, direction, up_score, result FROM predictions
                       WHERE horizon = ? ORDER BY timestamp DESC LIMIT 30""", (h,)
                ).fetchall()
                for h in HORIZONS
            }
    except (OSError, sqlite3.Error):
        return None

    summary = {h: dict.fromkeys(OUTCOMES, 0) for h in HORIZONS}
    for row in counts:
        h, result = row["horizon"], row["result"]
        if h in summary and result in OUTCOMES:
            summary[h][result] = row["count"]
    return {
        h: {
            "counts": summary[h],
            "records": [record for row in history[h] if (record := research_record(row, now))],
        }
        for h in HORIZONS
    }


def build_nifty_snapshot(data_dir, *, now=None):
    now = now or datetime.now(timezone.utc)
    state, candles, candle_analysis, quality = read_candles(data_dir / "latest.csv", now)
    predictions = read_predictions(data_dir / "predictions.db", now)
    last_close = quality.get("latest_completed_close_utc")

    signals = {}
    for horizon in HORIZONS:
        rows = predictions[horizon]["records"] if predictions is not None else []
        latest = rows[0] if rows else None
        label, reason = "NO TRADE", "No active research observation"
        if state != "LIVE DATA":
            reason = state.capitalize()
        elif latest and latest["result"] == "PENDING":
            if (pd.Timestamp(latest["time"]) == pd.Timestamp(last_close)
                    and now < pd.Timestamp(latest["expiry"])):
                label, reason = latest["direction"], "Active paper research observation"
        signals[horizon] = {"label": label, "reason": reason}

    return {
        "market": "NIFTY 50",
        "provider": "Upstox",
        "analysis_only": True,
        "execution_enabled": False,
        "checked_at": now.isoformat(),
        "state": state,
        "quality": quality,
        "candles": candles,
        "candle_analysis": candle_analysis,
        "signals": signals,
        "predictions": predictions,
    }
