"""Multi-timeframe analysis-only research strategy."""

import math
import pandas as pd

from indicators import calculate_indicators
from patterns.candlestick import detect_candlestick_patterns
from strategy.strategy_v2 import evaluate


def aggregate(frame, minutes):
    rule = f"{minutes}min"

    data = frame.set_index("timestamp").sort_index()

    grouped = data.resample(
        rule, label="left", closed="left"
    )

    candles = grouped.agg({
        "Open": "first",
        "High": "max",
        "Low": "min",
        "Close": "last"
    })

    counts = grouped["Close"].count()

    candles = candles.loc[counts == minutes].dropna()

    return candles.reset_index()


def trend(frame, fast=5, slow=10):
    if len(frame) < slow + 2:
        return 0

    close = frame["Close"].astype(float)

    ema_fast = close.ewm(
        span=fast, adjust=False
    ).mean()

    ema_slow = close.ewm(
        span=slow, adjust=False
    ).mean()

    c = close.iloc[-1]
    f = ema_fast.iloc[-1]
    s = ema_slow.iloc[-1]

    if c > f > s and f > ema_fast.iloc[-2]:
        return 1

    if c < f < s and f < ema_fast.iloc[-2]:
        return -1

    return 0


def evaluate_v3(
    frame,
    *,
    data_mode="unknown",
    data_quality_status="INVALID"
):
    def result(signal, reason, regime="UNKNOWN"):
        return {
            "model": "strategy_v3_mtf",
            "research_hypothesis": signal,
            "live_trading_signal": "NO TRADE",
            "expiry_minutes": 15,
            "market_regime": regime,
            "reason": reason,
            "execution_enabled": False
        }

    if (
        frame is None
        or len(frame) < 195
        or data_mode not in ("live", "delayed")
        or data_quality_status != "VALID"
    ):
        return result("NO TRADE", "Data safety gate")

    data = frame.copy()

    required = [
        "timestamp", "Open", "High", "Low", "Close"
    ]

    if not all(c in data.columns for c in required):
        return result("NO TRADE", "Missing columns")

    data["timestamp"] = pd.to_datetime(
        data["timestamp"], utc=True, errors="coerce"
    )

    if data.timestamp.isna().any():
        return result("NO TRADE", "Invalid timestamps")

    data = data.sort_values("timestamp")

    if data.timestamp.duplicated().any():
        return result("NO TRADE", "Duplicate candles")

    if not (
        data.timestamp.diff().dropna()
        == pd.Timedelta(minutes=1)
    ).all():
        return result("NO TRADE", "Candle gap")

    prices = data[["Open", "High", "Low", "Close"]]

    if not prices.map(math.isfinite).all().all():
        return result("NO TRADE", "Invalid prices")

    if (
        (prices <= 0).any().any()
        or (data.High < prices.max(axis=1)).any()
        or (data.Low > prices.min(axis=1)).any()
    ):
        return result("NO TRADE", "Invalid OHLC")

    # 1. Completed multi-timeframe candles
    m5 = aggregate(data, 5)
    m15 = aggregate(data, 15)

    if len(m5) < 12 or len(m15) < 12:
        return result(
            "NO TRADE", "Higher timeframe warmup"
        )

    t5 = trend(m5)
    t15 = trend(m15)

    # 2. Market regime detection
    close = data.Close.astype(float)

    movement = abs(
        close.iloc[-1] - close.iloc[-21]
    )

    path = close.diff().abs().iloc[-20:].sum()

    efficiency = movement / path if path > 0 else 0

    enriched = calculate_indicators(data.copy())
    patterns = detect_candlestick_patterns(data.copy())

    if "Pattern_Direction" in patterns:
        enriched["Pattern_Direction"] = (
            patterns["Pattern_Direction"].to_numpy()
        )

    r = enriched.iloc[-1]

    atr = float(r["ATR_14"])
    price = float(r["Close"])

    if not math.isfinite(atr) or atr <= 0:
        return result("NO TRADE", "Invalid ATR")

    atr_history = enriched["ATR_14"].iloc[-60:-1]
    normal_atr = float(atr_history.median())

    if not math.isfinite(normal_atr) or normal_atr <= 0:
        return result("NO TRADE", "ATR warmup")

    if atr > 2.5 * normal_atr:
        return result(
            "NO TRADE", "Extreme volatility", "VOLATILE"
        )

    if efficiency < 0.20:
        return result(
            "NO TRADE", "Range-bound market", "SIDEWAYS"
        )

    regime = (
        "TRENDING" if efficiency >= 0.40
        else "TRANSITION"
    )

    # 3. One-minute entry analysis
    base = evaluate(
        enriched,
        data_mode=data_mode,
        data_quality_status=data_quality_status
    )

    signal = base["research_hypothesis"]

    if signal not in ("UP", "DOWN"):
        return result(
            "NO TRADE", base["reason"], regime
        )

    direction = 1 if signal == "UP" else -1

    # 4. Higher timeframe confirmation
    if t5 != direction or t15 != direction:
        return result(
            "NO TRADE",
            f"Timeframe conflict: M5={t5}, M15={t15}",
            regime
        )

    # 5. False breakout and rejection detection
    candle = data.iloc[-1]
    previous = data.iloc[-21:-1]

    high = float(previous.High.max())
    low = float(previous.Low.min())

    candle_range = float(candle.High - candle.Low)

    if candle_range <= 0:
        return result(
            "NO TRADE", "Flat entry candle", regime
        )

    upper_wick = (
        candle.High - max(candle.Open, candle.Close)
    )

    lower_wick = (
        min(candle.Open, candle.Close) - candle.Low
    )

    if direction == 1:
        rejected = (
            candle.High > high and candle.Close <= high
        )
        weak_close = upper_wick / candle_range > 0.55
    else:
        rejected = (
            candle.Low < low and candle.Close >= low
        )
        weak_close = lower_wick / candle_range > 0.55

    if rejected or weak_close:
        return result(
            "NO TRADE", "Possible false breakout", regime
        )

    return result(
        signal,
        "M1 entry, M5 trend, M15 direction aligned",
        regime
    )
