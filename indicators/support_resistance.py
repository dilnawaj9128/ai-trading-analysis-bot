"""Rolling support/resistance from prior candles only (no look-ahead)."""
import pandas as pd
from ._utils import validate_ohlc, validate_period


def calculate_support_resistance(df: pd.DataFrame, window: int = 20) -> pd.DataFrame:
    window = validate_period(window)
    data = validate_ohlc(df)
    resistance = data["High"].rolling(window=window, min_periods=window).max().shift(1).rename("Resistance")
    support = data["Low"].rolling(window=window, min_periods=window).min().shift(1).rename("Support")
    return pd.concat([support, resistance], axis=1)
