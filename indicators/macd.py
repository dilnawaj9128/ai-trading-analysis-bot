"""Moving Average Convergence Divergence."""
import pandas as pd
from .ema import calculate_ema
from ._utils import as_series, validate_period


def calculate_macd(close, fast: int = 12, slow: int = 26, signal: int = 9) -> pd.DataFrame:
    fast = validate_period(fast)
    slow = validate_period(slow)
    signal = validate_period(signal)
    if fast >= slow:
        raise ValueError("fast period must be smaller than slow period")
    prices = as_series(close, "close")
    macd_line = calculate_ema(prices, fast) - calculate_ema(prices, slow)
    macd_line.name = "MACD"
    signal_line = macd_line.ewm(span=signal, adjust=False, min_periods=signal).mean().rename("MACD_signal")
    histogram = (macd_line - signal_line).rename("MACD_histogram")
    return pd.concat([macd_line, signal_line, histogram], axis=1)
