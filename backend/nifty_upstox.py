"""Read-only fallback for the current NIFTY 50 trading day's minute candles."""

from datetime import time
from threading import Lock
from time import monotonic
from zoneinfo import ZoneInfo

import pandas as pd
import requests

from dashboard.real_data_mode import validate_ohlc

IST = ZoneInfo("Asia/Kolkata")
OPEN = time(9, 15)
CLOSE = time(15, 30)
MINUTE = pd.Timedelta(minutes=1)
URL = "https://api.upstox.com/v3/historical-candle/intraday/NSE_INDEX%7CNifty%2050/minutes/1"
COLUMNS = ("timestamp", "Open", "High", "Low", "Close", "Volume", "OI")


def expected_close(now):
    """Latest regular-session minute close for today, when one is expected."""
    local = now.astimezone(IST)
    if local.weekday() >= 5 or local.time() < time(9, 16):
        return None
    if local.time() >= CLOSE:
        return pd.Timestamp(local.replace(hour=15, minute=30, second=0, microsecond=0))
    return pd.Timestamp(local.replace(second=0, microsecond=0))


def fetch_candles(token, now):
    response = requests.get(URL, headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
                            timeout=(2, 3), allow_redirects=False)
    if response.status_code in (401, 403):
        return None, {}, "Upstox rejected the access token"
    if response.status_code != 200:
        return None, {}, "Upstox candle request failed"

    payload = response.json()
    if payload.get("status") != "success":
        return None, {}, "Upstox candle request failed"
    frame = pd.DataFrame(payload["data"]["candles"], columns=COLUMNS)
    if frame.empty:
        return None, {}, "Upstox returned no candles for this session"
    if not frame["timestamp"].astype(str).str.contains(r"(?:Z|[+-]\d\d:\d\d)$", regex=True).all():
        raise ValueError("Candle timestamps must include offsets")

    frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True, errors="raise")
    local = frame["timestamp"].dt.tz_convert(IST)
    regular = (local.dt.date == now.astimezone(IST).date()) & (local.dt.time >= OPEN) & (local.dt.time < CLOSE)
    frame = frame.loc[regular & (frame["timestamp"] + MINUTE <= now)].sort_values("timestamp")
    if frame.empty:
        return None, {}, "Upstox returned no completed candles for this session"
    frame, quality = validate_ohlc(frame, now=now, min_rows=1)
    return frame, quality, None


class UpstoxMinuteFeed:
    """Share one request window across all dashboard tabs."""

    def __init__(self, token):
        self.token = token
        self.lock = Lock()
        self.next_attempt = 0
        self.result = (None, {}, None)

    def resolve(self, now, local_close):
        target = expected_close(now)
        with self.lock:
            frame, quality, note = self.result
            cached_close = quality.get("latest_completed_close_utc")
            if cached_close and pd.Timestamp(cached_close) > now:
                frame, quality, note = None, {}, None
                cached_close = None
            latest = max((pd.Timestamp(stamp) for stamp in (cached_close, local_close) if stamp), default=None)
            if target is not None and (latest is None or latest < target) and monotonic() >= self.next_attempt:
                self.next_attempt = monotonic() + (300 if now.astimezone(IST).time() >= CLOSE else 60)
                try:
                    fetched, fetched_quality, note = fetch_candles(self.token, now)
                    if fetched is not None and (cached_close is None or
                            pd.Timestamp(fetched_quality["latest_completed_close_utc"]) >= pd.Timestamp(cached_close)):
                        frame, quality = fetched, fetched_quality
                except (requests.RequestException, ValueError, TypeError, KeyError, AttributeError):
                    note = "Upstox candle response unavailable or invalid"
                self.result = (frame, quality, note)

            if frame is not None:
                age = (now - pd.Timestamp(quality["latest_completed_close_utc"])).total_seconds()
                quality = {**quality, "age_seconds": round(age, 1), "stale": age > 180}
            return frame, quality, note if target is not None else None
