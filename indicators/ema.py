"""Exponential moving average."""


def calculate_ema(close, period: int = 20):
    from ._utils import as_series, validate_period

    period = validate_period(period)
    values = as_series(close, "close")
    return values.ewm(span=period, adjust=False, min_periods=period).mean().rename(f"EMA_{period}")
