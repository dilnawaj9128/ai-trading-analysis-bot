
"""Twelve Data EUR/USD historical acquisition.

Research only. Does not trade or modify SQLite.
The API response is NOT proof of a verified feed mode.
"""

from datetime import datetime, timedelta, timezone
from pathlib import Path
from hashlib import sha256
from urllib.parse import urlencode
from urllib.request import urlopen
import json
import os

import pandas as pd

from simulator.historical_integrity import normalize_candles


API_URL = "https://api.twelvedata.com/time_series"


def _utc_datetime(value):
    if not isinstance(value, datetime):
        raise ValueError("Expected datetime.")

    if value.tzinfo is None:
        raise ValueError("Datetime must be timezone-aware.")

    return value.astimezone(timezone.utc)


def _format_api_time(value):
    return _utc_datetime(value).strftime(
        "%Y-%m-%d %H:%M:%S"
    )


def _sha256(path):
    digest = sha256()

    with Path(path).open("rb") as stream:
        for chunk in iter(
            lambda: stream.read(1024 * 1024), b""
        ):
            digest.update(chunk)

    return digest.hexdigest()


def _default_fetch(params, api_key):
    request_params = dict(params)
    request_params["apikey"] = api_key

    url = API_URL + "?" + urlencode(request_params)

    # Do not print the URL: it contains the API key.
    with urlopen(url, timeout=30) as response:
        return json.load(response)


def download_eurusd(
    *,
    start,
    end,
    output_dir,
    api_key=None,
    fetcher=None,
    retrieved_at=None,
):
    """Download and save a bounded 1-minute UTC dataset.

    fetcher is injectable for deterministic unit tests.
    """

    start = _utc_datetime(start)
    end = _utc_datetime(end)

    if end <= start:
        raise ValueError("end must be after start.")

    if start.second or start.microsecond:
        raise ValueError("start must be minute-aligned.")

    if end.second or end.microsecond:
        raise ValueError("end must be minute-aligned.")

    # Keep first stage small: no pagination yet.
    if end - start > timedelta(hours=6):
        raise ValueError(
            "Maximum request window is 6 hours."
        )

    key = api_key or os.getenv("TWELVE_DATA_API_KEY")

    if not key:
        raise ValueError(
            "TWELVE_DATA_API_KEY is missing."
        )

    params = {
        "symbol": "EUR/USD",
        "interval": "1min",
        "timezone": "UTC",
        "start_date": _format_api_time(start),
        "end_date": _format_api_time(end),
        "order": "asc",
        "outputsize": 5000,
        "format": "JSON",
    }

    if fetcher is None:
        payload = _default_fetch(params, key)
    else:
        payload = fetcher(params, key)

    if not isinstance(payload, dict):
        raise ValueError("Invalid API response.")

    if payload.get("status") == "error":
        raise ValueError(
            "Twelve Data API returned an error."
        )

    metadata = payload.get("meta", {})

    if not isinstance(metadata, dict):
        raise ValueError("Invalid API metadata.")

    if metadata.get("symbol") != "EUR/USD":
        raise ValueError("Unexpected API symbol.")

    if metadata.get("interval") != "1min":
        raise ValueError("Unexpected API interval.")

    values = payload.get("values")

    if not isinstance(values, list) or not values:
        raise ValueError("No historical candles returned.")

    if len(values) >= 5000:
        raise ValueError(
            "Potentially truncated API response."
        )

    received_at = _utc_datetime(
        retrieved_at or datetime.now(timezone.utc)
    )

    rows = []

    for item in values:
        if not isinstance(item, dict):
            raise ValueError("Invalid candle item.")

        # timezone=UTC was explicitly requested.
        # Twelve Data may return naive datetime strings
        # representing the requested timezone.
        raw_time = str(item["datetime"])

        timestamp = datetime.fromisoformat(
            raw_time.replace("Z", "+00:00")
        )

        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(
                tzinfo=timezone.utc
            )
        else:
            timestamp = timestamp.astimezone(
                timezone.utc
            )

        if timestamp.second or timestamp.microsecond:
            raise ValueError(
                "Candle timestamp not minute-aligned."
            )

        # Provider may include the exact end boundary.
        # Our research window uses an exclusive end.

        if timestamp == end:
            continue

        # Reject every other out-of-range timestamp.
        if not start <= timestamp < end:
            raise ValueError(
                f"Candle outside requested window: "
                f"raw={raw_time!r}, "
                f"parsed_utc={timestamp.isoformat()}, "
                f"start={start.isoformat()}, "
                f"end_exclusive={end.isoformat()}"
            )

        rows.append({
            "timestamp": timestamp,
            "Open": item["open"],
            "High": item["high"],
            "Low": item["low"],
            "Close": item["close"],
        })

    frame = pd.DataFrame(rows)

    if frame["timestamp"].duplicated().any():
        raise ValueError(
            "Duplicate timestamps in API response."
        )

    # Reject incomplete current candles.
    completed = frame[
        frame["timestamp"] + timedelta(minutes=1)
        <= received_at
    ].copy()

    if completed.empty:
        raise ValueError(
            "No completed candles available."
        )

    normalized = normalize_candles(completed)
    normalized = normalized.reset_index(drop=True)

    output_dir = Path(output_dir)
    output_dir.mkdir(
        parents=True, exist_ok=True
    )

    # Refuse overwriting an existing acquisition.
    csv_path = output_dir / "eurusd_1min_utc.csv"
    receipt_path = output_dir / "acquisition.json"

    if csv_path.exists() or receipt_path.exists():
        raise FileExistsError(
            "Output already exists. Use a new directory."
        )

    normalized.to_csv(
        csv_path, index=False,
        date_format="%Y-%m-%dT%H:%M:%S%z",
    )

    receipt = {
        "schema_version": 1,
        "provider": "Twelve Data",
        "symbol": "EUR/USD",
        "timeframe": "1min",
        "requested_timezone": "UTC",
        "timestamp_semantics": "candle_open_utc",
        "requested_start": start.isoformat(),
        "requested_end": end.isoformat(),
        "retrieved_at": received_at.isoformat(),
        "candle_count": len(normalized),
        "csv_sha256": _sha256(csv_path),
        "feed_mode": "unknown",
        "provider_feed_mode_verified": False,
        "broker_verified": False,
        "research_only": True,
        "source_endpoint": API_URL,
    }

    receipt_path.write_text(
        json.dumps(receipt, indent=2),
        encoding="utf-8",
    )

    return csv_path, receipt_path

