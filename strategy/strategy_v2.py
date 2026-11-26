"""Experimental analysis-only strategy V2."""

import math


def evaluate(data, *, data_mode="unknown",
             data_quality_status="INVALID"):

    def result(signal, reason):
        return {
            "research_hypothesis": signal,
            "live_trading_signal": "NO TRADE",
            "reason": reason,
            "execution_enabled": False
        }

    if (
        data is None
        or len(data) < 60
        or data_mode not in ("live", "delayed")
        or data_quality_status != "VALID"
    ):
        return result("NO TRADE", "Data safety gate")

    r = data.iloc[-1]
    p = data.iloc[-2]

    try:
        c, e, f, a, s, m, lo, hi = [
            float(r[k]) for k in (
                "Close", "EMA_20", "EMA_50",
                "ATR_14", "RSI_14",
                "MACD_histogram",
                "Support", "Resistance"
            )
        ]

        pm = float(p["MACD_histogram"])
        pe = float(p["EMA_20"])
        pc = float(p["Close"])

        values = (c, e, f, a, s, m, lo, hi, pm, pe, pc)

        if (
            not all(map(math.isfinite, values))
            or a <= 0
            or c <= 0
            or not 0 <= s <= 100
            or lo > hi
        ):
            raise ValueError()

    except (KeyError, ValueError, TypeError):
        return result("NO TRADE", "Invalid indicators")

    reasons = []

    for d in (1, -1):

        direction = "UP" if d == 1 else "DOWN"

        # Improvement 1: Market regime
        trend = d * (c - e) > 0 and d * (e - f) > 0

        emerging = (
            d * (c - e) > 0
            and d * (e - pe) > 0
            and abs(e - f) <= 0.25 * a
            and d * m > 0
        )

        if not (trend or emerging):
            reasons.append(f"{direction}: No clear trend")
            continue

        # Improvement 2: Adaptive momentum
        momentum = (
            30 < s < 70
            and d * (s - 50) > 0
            and d * m > 0
            and (
                d * (m - pm) > 0
                or d * (s - 50) > 5
            )
        )

        if not momentum:
            reasons.append(f"{direction}: Weak momentum")
            continue

        # Improvement 3: Breakout analysis
        level = hi if d == 1 else lo
        distance = d * (level - c)

        breakout = (
            d * (c - level) > 0.1 * a
            and d * (pc - level) <= 0
        )

        if distance <= 0.25 * a and not breakout:
            reasons.append(f"{direction}: Level obstruction")
            continue

        patterns = [
            x.strip() for x in
            str(r.get("Pattern_Direction", "NONE"))
            .upper().split(";")
        ]

        opposite = "BEARISH" if d == 1 else "BULLISH"

        if opposite in patterns:
            reasons.append(f"{direction}: Pattern conflict")
            continue

        return result(
            direction,
            "Trend, momentum and level checks aligned"
        )

    return result("NO TRADE", "; ".join(reasons))
