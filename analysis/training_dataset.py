"""Research-only 15-minute ML training dataset builder."""

from pathlib import Path

import numpy as np
import pandas as pd

from indicators import calculate_ema, calculate_indicators

HORIZON = 15
REQUIRED = ("timestamp", "Open", "High", "Low", "Close")


def validate_1m_frame(frame):
    if not isinstance(frame, pd.DataFrame):
        raise ValueError("Expected pandas DataFrame")

    if frame.empty or not set(REQUIRED).issubset(frame.columns):
        raise ValueError("Missing OHLC data")

    data = frame.loc[:, list(REQUIRED)].copy()

    data["timestamp"] = pd.to_datetime(
        data["timestamp"], utc=True, errors="raise"
    )

    if (
        data["timestamp"].isna().any()
        or data["timestamp"].duplicated().any()
    ):
        raise ValueError("Invalid or duplicate timestamps")

    data = data.sort_values("timestamp").reset_index(drop=True)

    if (
        data["timestamp"].dt.second.ne(0).any()
        or data["timestamp"].dt.microsecond.ne(0).any()
    ):
        raise ValueError("Misaligned timestamps")

    for col in REQUIRED[1:]:
        data[col] = pd.to_numeric(data[col], errors="raise")

    prices = data[list(REQUIRED[1:])]

    if not np.isfinite(prices.to_numpy(dtype=float)).all():
        raise ValueError("Non-finite prices")

    if (prices <= 0).any().any():
        raise ValueError("Non-positive prices")

    if (
        (data["High"] < data[["Open", "Close", "Low"]].max(axis=1))
        | (data["Low"] > data[["Open", "Close", "High"]].min(axis=1))
    ).any():
        raise ValueError("Invalid OHLC relationships")

    return data


def build_training_dataset(frame, *, horizon_minutes=15):
    if type(horizon_minutes) is not int or horizon_minutes != 15:
        raise ValueError("Only 15-minute horizon supported")

    data = validate_1m_frame(frame)

    if len(data) < 75:
        raise ValueError("At least 75 candles required")

    # Indicators use historical/current candles only.
    enriched = calculate_indicators(data.copy())

    enriched["EMA_9"] = calculate_ema(enriched["Close"], 9)
    enriched["EMA_21"] = calculate_ema(enriched["Close"], 21)

    enriched["return_1m"] = enriched["Close"].pct_change()
    enriched["return_5m"] = enriched["Close"].pct_change(5)

    enriched["range_pct"] = (
        enriched["High"] - enriched["Low"]
    ) / enriched["Close"]

    enriched["ema_gap_pct"] = (
        enriched["EMA_9"] - enriched["EMA_21"]
    ) / enriched["Close"]

    enriched["volatility_10"] = (
        enriched["return_1m"].rolling(10).std()
    )

    features = [
        "EMA_9",
        "EMA_21",
        "RSI_14",
        "return_1m",
        "return_5m",
        "range_pct",
        "ema_gap_pct",
        "volatility_10",
    ]

    for col in ("MACD", "MACD_Signal", "ATR_14"):
        if col in enriched.columns:
            features.append(col)

    step = pd.Timedelta(minutes=1)

    # All 15 consecutive intervals must exist.
    contiguous = enriched["timestamp"].diff().eq(step)

    valid_window = (
        contiguous.rolling(15, min_periods=15)
        .sum()
        .shift(-15)
        .eq(15)
    )

    future_close = enriched["Close"].shift(-15)
    future_timestamp = enriched["timestamp"].shift(-15)

    future_return = (
        future_close / enriched["Close"] - 1
    )

    valid_window = valid_window & (
        future_timestamp - enriched["timestamp"]
    ).eq(pd.Timedelta(minutes=15))

    result = enriched[["timestamp", *features]].copy()

    result["outcome_timestamp"] = future_timestamp
    result["future_return_15m"] = future_return

    result["label_up_15m"] = (
        future_return > 0
    ).astype("int64")

    result = result.loc[valid_window]
    result = result.replace([np.inf, -np.inf], np.nan)

    result = result.dropna(
        subset=[*features, "future_return_15m"]
    )

    return result.reset_index(drop=True)


def save_training_dataset(dataset, path):
    path = Path(path)

    if path.exists():
        raise FileExistsError(path)

    if not isinstance(dataset, pd.DataFrame) or dataset.empty:
        raise ValueError("Non-empty dataset required")

    path.parent.mkdir(parents=True, exist_ok=True)

    dataset.to_csv(path, index=False, mode="x")

    return path
