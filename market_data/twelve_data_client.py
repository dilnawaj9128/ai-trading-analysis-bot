
"""Research-only Twelve Data REST client.

Safety:
- No broker API, orders, or trading signals.
- Conservative persistent request-budget guard.
- Explicit UTC timestamps and OHLC validation.
- Manual fetch only in Stage 7.2.
"""

from __future__ import annotations

import fcntl
import json
import math
import os
import time
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import requests

from config.market_config import (
    ResearchConfig,
    create_research_config,
)

API_URL = "https://api.twelvedata.com/time_series"
STATE_PATH = Path("data/api_usage/twelve_data_budget.json")

# Conservative local limits, not a guarantee of account entitlements.
MINUTE_LIMIT = 8
DAY_LIMIT = 800
RESERVE_PER_REQUEST = 1
TIMEOUT_SECONDS = 15
MAX_CANDLES = 120

INTERVAL_SECONDS = {
    "1min": 60,
    "5min": 300,
    "15min": 900,
}


class MarketDataError(RuntimeError):
    pass


class BudgetExceeded(MarketDataError):
    pass


def utc_now():
    return datetime.now(timezone.utc)


def _validate_limits():
    if MINUTE_LIMIT < 1 or DAY_LIMIT < 1:
        raise MarketDataError("Invalid local API budget limits")
    if RESERVE_PER_REQUEST < 1:
        raise MarketDataError("Invalid request reservation")



def _save_budget_atomic(path, payload):
    """Atomically replace the budget state and sync its directory."""
    temporary = None

    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=".budget_",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary = Path(handle.name)
            json.dump(payload, handle, indent=2)
            handle.flush()
            os.fsync(handle.fileno())

        os.replace(temporary, path)

        directory_fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)

    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def reserve_request(path=STATE_PATH, now=None):
    """Reserve estimated API usage before network access.

    Uses a separate stable lock file and atomic budget-state writes.
    Reservations are never automatically refunded.
    """
    _validate_limits()

    now = now or utc_now()
    if now.tzinfo is None:
        raise MarketDataError("Budget time must be timezone-aware")

    now = now.astimezone(timezone.utc)
    minute = now.strftime("%Y-%m-%dT%H:%MZ")
    day = now.strftime("%Y-%m-%d")

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    lock_path = path.with_name(path.name + ".lock")

    with lock_path.open("a+b") as lock_file:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)

        try:
            # Fail closed if the lock path was replaced.
            locked = os.fstat(lock_file.fileno())
            current = os.stat(lock_path)

            if (
                locked.st_dev != current.st_dev
                or locked.st_ino != current.st_ino
            ):
                raise MarketDataError(
                    "Budget lock identity changed"
                )

            try:
                raw = path.read_text(encoding="utf-8")
            except FileNotFoundError:
                # Only a genuinely missing file is a fresh budget.
                state = {}
            else:
                if not raw.strip():
                    raise MarketDataError(
                        "Existing budget state empty or corrupted; "
                        "refusing API request"
                    )

                try:
                    state = json.loads(raw)
                except json.JSONDecodeError as exc:
                    raise MarketDataError(
                        "Budget state corrupted; refusing API request"
                    ) from exc

            if not isinstance(state, dict):
                raise MarketDataError("Invalid budget state")

            if state.get("minute") != minute:
                minute_used = 0
            else:
                minute_used = state.get("minute_used", 0)

            if state.get("day") != day:
                day_used = 0
            else:
                day_used = state.get("day_used", 0)

            if (
                type(minute_used) is not int
                or type(day_used) is not int
                or minute_used < 0
                or day_used < 0
            ):
                raise MarketDataError("Invalid budget counters")

            if minute_used + RESERVE_PER_REQUEST > MINUTE_LIMIT:
                raise BudgetExceeded("Local minute budget exhausted")

            if day_used + RESERVE_PER_REQUEST > DAY_LIMIT:
                raise BudgetExceeded("Local daily budget exhausted")

            updated = {
                "minute": minute,
                "minute_used": minute_used + RESERVE_PER_REQUEST,
                "day": day,
                "day_used": day_used + RESERVE_PER_REQUEST,
            }

            _save_budget_atomic(path, updated)
            return updated

        finally:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)



def parse_candles(payload, config, now=None):
    """Parse and validate recent OHLC candles.

    Returned candles are research-only. In-progress candles
    are excluded conservatively using UTC interval boundaries.
    """
    now = now or utc_now()
    if now.tzinfo is None:
        raise MarketDataError("Current time must have a timezone")
    now = now.astimezone(timezone.utc)

    if not isinstance(payload, dict):
        raise MarketDataError("Invalid API response structure")

    if payload.get("status") == "error" or payload.get("code"):
        raise MarketDataError(
            f"Provider rejected request: {payload.get('message', 'unknown')}"
        )

    values = payload.get("values")
    if not isinstance(values, list) or not values:
        raise MarketDataError("API returned no candles")

    metadata = payload.get("meta")
    if not isinstance(metadata, dict):
        raise MarketDataError("Missing provider metadata")

    returned_symbol = metadata.get("symbol")
    returned_interval = metadata.get("interval")

    if returned_symbol != config.symbol:
        raise MarketDataError("Provider symbol mismatch")

    if returned_interval != config.timeframe:
        raise MarketDataError("Provider interval mismatch")

    interval = INTERVAL_SECONDS[config.timeframe]
    rows = []
    seen = set()

    for item in values:
        if not isinstance(item, dict):
            raise MarketDataError("Malformed candle")

        try:
            stamp = datetime.strptime(
                item["datetime"], "%Y-%m-%d %H:%M:%S"
            ).replace(tzinfo=timezone.utc)

            o = float(item["open"])
            h = float(item["high"])
            l = float(item["low"])
            c = float(item["close"])
        except (KeyError, ValueError, TypeError) as exc:
            raise MarketDataError("Invalid candle fields") from exc

        if not all(math.isfinite(x) for x in (o, h, l, c)):
            raise MarketDataError("Non-finite OHLC value")

        if l > min(o, c) or h < max(o, c) or l > h:
            raise MarketDataError("Invalid OHLC relationship")

        if min(o, h, l, c) <= 0:
            raise MarketDataError("Non-positive OHLC value")

        if stamp in seen:
            raise MarketDataError("Duplicate candle timestamp")
        seen.add(stamp)

        if stamp > now:
            raise MarketDataError("Future candle timestamp")

        # Exclude candles whose interval has not yet ended.
        if stamp + timedelta(seconds=interval) > now:
            continue

        rows.append({
            "timestamp": stamp,
            "Open": o,
            "High": h,
            "Low": l,
            "Close": c,
        })

    if not rows:
        raise MarketDataError("No completed candles available")

    frame = pd.DataFrame(rows).sort_values("timestamp")
    frame = frame.reset_index(drop=True)

    # Never silently treat gaps as continuous data.
    diffs = frame["timestamp"].diff().dropna()
    gaps = int((diffs > pd.Timedelta(seconds=interval)).sum())

    latest = frame["timestamp"].iloc[-1].to_pydatetime()
    age_seconds = (now - latest).total_seconds()

    # A conservative monitoring rule, not proof of feed quality.
    stale = age_seconds > interval * 3

    return {
        "frame": frame,
        "symbol": config.symbol,
        "interval": config.timeframe,
        "candles": len(frame),
        "gaps": gaps,
        "latest_utc": latest.isoformat(),
        "age_seconds": age_seconds,
        "stale": stale,
        "analysis_only": True,
        "execution_enabled": False,
        "directional_backtesting_allowed": False,
    }


def fetch_recent_candles(
    config: ResearchConfig,
    *,
    api_key=None,
    state_path=STATE_PATH,
    now=None,
    session=None,
):
    """Fetch recent candles with budget reservation first."""

    # Revalidate even if caller constructs a dataclass directly.
    validated = create_research_config(
        config.platform,
        config.market,
        config.symbol,
        config.timeframe,
        config.expiry_minutes,
    )

    if config != validated:
        raise MarketDataError("Unsafe or modified research config")

    key = (
        api_key
        if api_key is not None
        else os.environ.get("TWELVE_DATA_API_KEY")
    )
    if not key:
        raise MarketDataError("TWELVE_DATA_API_KEY is missing")

    now = now or utc_now()
    if now.tzinfo is None:
        raise MarketDataError("Current time must have a timezone")
    now = now.astimezone(timezone.utc)

    reserve_request(state_path, now=now)

    client = session if session is not None else requests

    try:
        response = client.get(
            API_URL,
            params={
                "symbol": config.symbol,
                "interval": config.timeframe,
                "outputsize": MAX_CANDLES,
                "timezone": "UTC",
                "apikey": key,
                "format": "JSON",
            },
            timeout=TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        payload = response.json()
    except (requests.RequestException, ValueError) as exc:
        raise MarketDataError(
            "Twelve Data request failed or returned invalid JSON"
        ) from exc

    return parse_candles(payload, config, now=now)

