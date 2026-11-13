from datetime import datetime, timezone
from unittest.mock import patch

import pandas as pd
import pytest

from config.market_config import create_research_config
from market_data.historical_collector import (
    _validate_historical_request,
)


NOW = datetime(2026, 11, 13, 12, 0, tzinfo=timezone.utc)


def config():
    return create_research_config(
        "quotex", "forex", "EUR/USD", "1min", 15
    )


def validate(**overrides):
    args = {
        "start": "2026-11-12T10:00:00Z",
        "end": "2026-11-12T10:01:00Z",
        "now": NOW,
        "api_key": "mock-key",
        "outputsize": 10,
    }
    args.update(overrides)
    return _validate_historical_request(config(), **args)


def test_valid_request():
    start, end, now, step, key = validate()

    assert start == pd.Timestamp("2026-11-12T10:00:00Z")
    assert end == pd.Timestamp("2026-11-12T10:01:00Z")
    assert step == pd.Timedelta(minutes=1)
    assert key == "mock-key"


def test_future_range_rejected():
    with pytest.raises(ValueError):
        validate(end="2026-11-14T10:00:00Z")


def test_reversed_range_rejected():
    with pytest.raises(ValueError):
        validate(
            start="2026-11-12T10:01:00Z",
            end="2026-11-12T10:00:00Z",
        )


def test_naive_timestamp_rejected():
    with pytest.raises(ValueError):
        validate(start="2026-11-12T10:00:00")


def test_misaligned_timestamp_rejected():
    with pytest.raises(ValueError):
        validate(start="2026-11-12T10:00:30Z")


def test_invalid_outputsize_rejected():
    with pytest.raises(ValueError):
        validate(outputsize=0)


def test_missing_api_key_rejected(monkeypatch):
    monkeypatch.delenv("TWELVE_DATA_API_KEY", raising=False)

    with pytest.raises(Exception, match="API_KEY"):
        validate(api_key="")


def test_validation_does_not_reserve_budget():
    with patch(
        "market_data.historical_collector.reserve_request"
    ) as reserve:
        validate()

    reserve.assert_not_called()
