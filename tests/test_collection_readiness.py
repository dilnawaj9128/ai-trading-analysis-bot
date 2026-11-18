import pytest

from analysis.collection_readiness import (
    calculate_collection_readiness,
)


def test_current_dataset():
    result = calculate_collection_readiness(
        raw_candles=120,
        eligible_rows=80,
    )

    assert result["missing_eligible_rows"] == 636
    assert result["estimated_total_raw_candles"] == 756
    assert result["collection_authorized"] is False


def test_enough_eligible_rows():
    result = calculate_collection_readiness(
        raw_candles=800,
        eligible_rows=760,
    )

    assert result["sufficient_rows"] is True
    assert result["estimated_additional_raw_candles"] == 0


def test_invalid_counts():
    with pytest.raises(ValueError):
        calculate_collection_readiness(
            raw_candles=100,
            eligible_rows=120,
        )


def test_boolean_rejected():
    with pytest.raises(ValueError):
        calculate_collection_readiness(
            raw_candles=True,
            eligible_rows=80,
        )
