"""Rolling per-candle return volatility (not annualized)."""
from ._utils import as_series, validate_period


def calculate_volatility(close, period: int = 20):
    period = validate_period(period)
    prices = as_series(close, "close")
    if (prices <= 0).any():
        raise ValueError("close prices must be positive")
    returns = prices.pct_change(fill_method=None)
    return (returns.rolling(window=period, min_periods=period).std(ddof=0) * 100.0).rename(f"Volatility_{period}_pct")
