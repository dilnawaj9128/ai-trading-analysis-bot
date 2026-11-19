"""Offline, analysis-only 15-minute research backtest. No network or orders.

Signal formed at CLOSE of bar i, settled at CLOSE of bar i+15. Strictly
contiguous 1-minute bars required over lookback and horizon. This approximates
an idealized entry at signal-candle close; not broker/executable fills.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import pandas as pd


class BacktestDataError(ValueError):
    pass


REQUIRED = ("timestamp", "Open", "High", "Low", "Close")


def load_candles(path: str | Path) -> pd.DataFrame:
    raw = pd.read_csv(path)
    if not set(REQUIRED).issubset(raw.columns):
        raise BacktestDataError("CSV needs timestamp,Open,High,Low,Close")
    df = raw[list(REQUIRED)].copy()
    stamps = df["timestamp"].astype(str)
    if not stamps.str.contains(r"(?:Z|[+-]\d{2}:\d{2})$", regex=True).all():
        raise BacktestDataError("Timestamps must have explicit UTC offsets")
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True, errors="raise")
    if df["timestamp"].isna().any() or df["timestamp"].duplicated().any():
        raise BacktestDataError("Missing or duplicate timestamps")
    if not df["timestamp"].is_monotonic_increasing:
        raise BacktestDataError("Candle timestamps must be ascending")
    if (df["timestamp"].dt.second != 0).any() or (df["timestamp"].dt.microsecond != 0).any():
        raise BacktestDataError("Candles must align to whole minutes")
    for col in REQUIRED[1:]:
        df[col] = pd.to_numeric(df[col], errors="raise")
        if not df[col].map(lambda x: math.isfinite(x) and x > 0).all():
            raise BacktestDataError("Nonfinite/nonpositive price")
    if not (df.High >= df[["Open", "Close", "Low"]].max(axis=1)).all():
        raise BacktestDataError("Bad High")
    if not (df.Low <= df[["Open", "Close", "High"]].min(axis=1)).all():
        raise BacktestDataError("Bad Low")
    return df.reset_index(drop=True)


def existing_strategy_on_prefix(prefix: pd.DataFrame) -> str:
    """Research simulation only: bypass provenance *only for offline scoring*.

    Never use this function for a live UI or to assert provider/broker parity.
    Indicator calculations use the supplied historical prefix only.
    """
    from indicators import calculate_indicators
    from strategy.signal_engine import generate_signal
    enriched = calculate_indicators(prefix.copy())
    # Existing engine uses Pattern_Direction when supplied. Compute on prefix.
    from patterns.candlestick import detect_candlestick_patterns
    patterns = detect_candlestick_patterns(prefix.copy())
    if "Pattern_Direction" in patterns.columns:
        enriched["Pattern_Direction"] = patterns["Pattern_Direction"].to_numpy()
    return generate_signal(
        enriched, expiry_minutes=15, data_mode="live",
        data_quality_status="VALID",
    )["signal"]


def summarize(trades: list[dict], no_trade: int, skipped: int, checked: int, payout: float) -> dict:
    wins = sum(x["result"] == "WIN" for x in trades)
    losses = sum(x["result"] == "LOSS" for x in trades)
    pushes = sum(x["result"] == "PUSH" for x in trades)
    resolved = wins + losses
    win_rate = wins / resolved if resolved else None
    pnl = round(wins * payout - losses, 8)  # pushes refund stake
    return {
        "signals": len(trades), "wins": wins, "losses": losses, "pushes": pushes,
        "resolved": resolved, "win_rate": win_rate, "no_trade": no_trade,
        "skipped_windows": skipped, "checked_windows": checked,
        "net_units": pnl, "payout": payout,
        "breakeven_win_rate": 1 / (1 + payout),
        "caution": "Hypothetical candle-close entry, not Quotex price/payout/latency parity",
    }


def backtest(df: pd.DataFrame, *, signal_fn: Callable[[pd.DataFrame], str] = existing_strategy_on_prefix,
             expiry: int = 15, warmup: int = 60, lookback: int = 60,
             payout: float = 0.80, holdout_fraction: float = 0.30,
             nonoverlap: bool = True) -> dict:
    if expiry != 15 or warmup < 60 or lookback < 2 or not 0 < holdout_fraction < 1:
        raise ValueError("Requires 15m expiry, warmup >=60 and holdout 0..1")
    if not 0 < payout <= 1:
        raise ValueError("Payout must be between 0 and 1")
    if not isinstance(df, pd.DataFrame) or not set(REQUIRED).issubset(df):
        raise BacktestDataError("Validated OHLC DataFrame required")
    # In-memory data must meet the same strict checks as CSV.
    if len(df) < warmup + expiry + 1:
        raise BacktestDataError("Insufficient candles for meaningful evaluation")
    data = df.reset_index(drop=True).copy()
    if data["timestamp"].isna().any() or data["timestamp"].dt.tz is None:
        raise BacktestDataError("UTC timestamps required")
    if data["timestamp"].duplicated().any() or not data["timestamp"].is_monotonic_increasing:
        raise BacktestDataError("Timestamps must be unique and sorted")
    split = max(warmup, int(len(data) * (1 - holdout_fraction)))
    delta = data.timestamp.diff().eq(pd.Timedelta(minutes=1))
    rows = []
    scores = {"training": {"no_trade": 0, "skipped": 0, "checked": 0},
              "holdout": {"no_trade": 0, "skipped": 0, "checked": 0}}
    i = warmup - 1
    while i + expiry < len(data):
        partition = "training" if i + expiry < split else "holdout" if i >= split else "boundary"
        # Don't allow training outcomes to cross into evaluation holdout.
        if partition == "boundary":
            i += 1
            continue
        stats = scores[partition]
        # Timestamp continuity is required for both indicator lookback and expiry.
        window_start = max(0, i - lookback + 1)
        if not delta.iloc[window_start + 1:i + expiry + 1].all():
            stats["skipped"] += 1
            i += 1
            continue
        # Prefix ends at i. Future bars never reach signal_fn.
        prefix = data.iloc[:i + 1].copy()
        signal = signal_fn(prefix)
        if signal not in ("UP", "DOWN", "NO TRADE"):
            raise ValueError("Unexpected strategy signal")
        stats["checked"] += 1
        if signal == "NO TRADE":
            stats["no_trade"] += 1
            i += 1
            continue
        entry = float(data.Close.iloc[i])
        exit_price = float(data.Close.iloc[i + expiry])
        outcome = "PUSH" if exit_price == entry else (
            "WIN" if (exit_price > entry) == (signal == "UP") else "LOSS"
        )
        rows.append({
            "partition": partition, "signal_time_utc": data.timestamp.iloc[i].isoformat(),
            "entry_time_utc": (data.timestamp.iloc[i] + pd.Timedelta(minutes=1)).isoformat(),
            "exit_time_utc": (data.timestamp.iloc[i + expiry] + pd.Timedelta(minutes=1)).isoformat(),
            "signal": signal, "entry_close": entry, "exit_close": exit_price,
            "result": outcome,
        })
        i += expiry if nonoverlap else 1
    return {
        "training": summarize([t for t in rows if t["partition"] == "training"], **scores["training"], payout=payout),
        "holdout": summarize([t for t in rows if t["partition"] == "holdout"], **scores["holdout"], payout=payout),
        "trades": rows,
        "method": "Completed candles; chronological split; independent 15m settlements; nonoverlap=" + str(nonoverlap),
    }
