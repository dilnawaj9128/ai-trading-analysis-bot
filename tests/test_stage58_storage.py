from datetime import datetime, timezone

import pytest

from market_data.providers.candle_repository import (
    CandleRepository,
)


def sample_candle():
    return {
        "timestamp": datetime(
            2026, 11, 22, 10, 0,
            tzinfo=timezone.utc
        ),
        "open": 1.1000,
        "high": 1.1020,
        "low": 1.0990,
        "close": 1.1010,
    }


def test_save_candle(tmp_path):
    repo = CandleRepository(tmp_path / "test.db")

    assert repo.save_candle(sample_candle()) is True
    assert repo.count_candles() == 1


def test_duplicate_candle(tmp_path):
    repo = CandleRepository(tmp_path / "test.db")

    repo.save_candle(sample_candle())

    assert repo.save_candle(sample_candle()) is False
    assert repo.count_candles() == 1


def test_invalid_ohlc(tmp_path):
    repo = CandleRepository(tmp_path / "test.db")

    candle = sample_candle()
    candle["high"] = 1.0000

    with pytest.raises(ValueError):
        repo.save_candle(candle)


def test_database_persistence(tmp_path):
    path = tmp_path / "test.db"

    repo1 = CandleRepository(path)
    repo1.save_candle(sample_candle())

    repo2 = CandleRepository(path)

    assert repo2.count_candles() == 1


def test_separate_sources(tmp_path):
    repo = CandleRepository(tmp_path / "test.db")

    assert repo.save_candle(
        sample_candle(), source="SIMULATED"
    )
    assert repo.save_candle(
        sample_candle(), source="VERIFIED_TEST"
    )

    assert repo.count_candles() == 2
