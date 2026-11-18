"""Shared input validation for technical indicators."""
import numpy as np
import pandas as pd


def validate_period(period: int) -> int:
    if isinstance(period, bool) or not isinstance(period, int) or period < 1:
        raise ValueError("period must be a positive integer")
    return period


def as_series(values, name: str = "values") -> pd.Series:
    series = values.copy() if isinstance(values, pd.Series) else pd.Series(values)
    series = pd.to_numeric(series, errors="coerce").astype("float64")
    if series.empty:
        raise ValueError(f"{name} cannot be empty")
    if not np.isfinite(series.to_numpy()).all():
        raise ValueError(f"{name} must contain only finite numeric values")
    return series


def validate_ohlc(df: pd.DataFrame) -> pd.DataFrame:
    required = ["High", "Low", "Close"]
    missing = set(required) - set(df.columns)
    if missing:
        raise ValueError(f"Missing OHLC columns: {sorted(missing)}")
    out = df.copy()
    for col in required:
        out[col] = pd.to_numeric(out[col], errors="coerce")
    if out[required].isna().any().any():
        raise ValueError("OHLC columns must contain finite numeric values")
    if not np.isfinite(out[required].to_numpy(dtype="float64")).all():
        raise ValueError("OHLC columns must contain finite numeric values")
    if (out["High"] < out["Low"]).any():
        raise ValueError("High cannot be below Low")
    if (out["High"] < out["Close"]).any() or (out["Low"] > out["Close"]).any():
        raise ValueError("Close must be between High and Low")
    return out
