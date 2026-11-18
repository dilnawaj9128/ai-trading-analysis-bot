"""Average True Range using Wilder smoothing."""
import numpy as np
import pandas as pd
from ._utils import validate_ohlc, validate_period


def calculate_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    period = validate_period(period)
    data = validate_ohlc(df)
    previous_close = data["Close"].shift(1)
    true_range = pd.concat([
        data["High"] - data["Low"],
        (data["High"] - previous_close).abs(),
        (data["Low"] - previous_close).abs(),
    ], axis=1).max(axis=1)

    values = true_range.to_numpy(dtype="float64")
    result = np.full(len(values), np.nan, dtype="float64")
    if len(values) >= period:
        result[period - 1] = values[:period].mean()
        for i in range(period, len(values)):
            result[i] = ((period - 1) * result[i - 1] + values[i]) / period
    return pd.Series(result, index=data.index, name=f"ATR_{period}")
