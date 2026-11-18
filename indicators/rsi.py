"""Relative Strength Index using Wilder's original smoothing method."""
import numpy as np
import pandas as pd


def calculate_rsi(close, period: int = 14) -> pd.Series:
    from ._utils import as_series, validate_period

    period = validate_period(period)
    prices = as_series(close, "close")
    result = np.full(len(prices), np.nan, dtype="float64")
    if len(prices) <= period:
        return pd.Series(result, index=prices.index, name=f"RSI_{period}")

    changes = prices.diff().to_numpy(dtype="float64")
    gains = np.maximum(changes, 0.0)
    losses = np.maximum(-changes, 0.0)
    avg_gain = float(gains[1:period + 1].mean())
    avg_loss = float(losses[1:period + 1].mean())

    def rsi_value(gain, loss):
        if loss == 0 and gain == 0:
            return 50.0
        if loss == 0:
            return 100.0
        if gain == 0:
            return 0.0
        rs = gain / loss
        return 100.0 - (100.0 / (1.0 + rs))

    result[period] = rsi_value(avg_gain, avg_loss)
    for i in range(period + 1, len(prices)):
        avg_gain = ((period - 1) * avg_gain + gains[i]) / period
        avg_loss = ((period - 1) * avg_loss + losses[i]) / period
        result[i] = rsi_value(avg_gain, avg_loss)

    return pd.Series(result, index=prices.index, name=f"RSI_{period}")
