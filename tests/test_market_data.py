
from datetime import datetime, timezone

import pandas as pd

from data.data_validator import DataValidator


def make_data():

    return pd.DataFrame({
        "timestamp": pd.to_datetime([
            "2026-11-10 10:00:00",
            "2026-11-10 10:01:00",
            "2026-11-10 10:02:00"
        ], utc=True),

        "Open": [1.10, 1.11, 1.12],
        "High": [1.12, 1.13, 1.14],
        "Low": [1.09, 1.10, 1.11],
        "Close": [1.11, 1.12, 1.13],
        "Volume": [100, 120, 150]
    })


def test_valid_data():

    validator = DataValidator()

    result = validator.validate(
        make_data(),
        interval_seconds=60,
        max_staleness_seconds=180,
        now=datetime(
            2026, 11, 10, 10, 3, 30,
            tzinfo=timezone.utc
        )
    )

    assert result.status == "VALID"
    assert result.total_candles == 3


def test_duplicate_detection():

    validator = DataValidator()

    data = make_data()

    data = pd.concat(
        [data, data.iloc[[1]]],
        ignore_index=True
    )

    result = validator.validate(
        data,
        interval_seconds=60,
        max_staleness_seconds=180,
        now=datetime(
            2026, 11, 10, 10, 3, 30,
            tzinfo=timezone.utc
        )
    )

    assert result.duplicate_candles == 1


def test_invalid_ohlc_detection():

    validator = DataValidator()

    data = make_data()

    data.loc[0, "High"] = 1.00

    result = validator.validate(
        data,
        interval_seconds=60,
        max_staleness_seconds=180,
        now=datetime(
            2026, 11, 10, 10, 3, 30,
            tzinfo=timezone.utc
        )
    )

    assert result.invalid_candles == 1


def test_stale_data():

    validator = DataValidator()

    result = validator.validate(
        make_data(),
        interval_seconds=60,
        max_staleness_seconds=60,
        now=datetime(
            2026, 11, 10, 10, 10, 0,
            tzinfo=timezone.utc
        )
    )

    assert result.status == "STALE"

