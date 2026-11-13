import pytest

from market_data.api_credit_monitor import parse_credit_headers


def test_valid_credit_headers():
    result = parse_credit_headers({
        "api-credits-used": "5",
        "api-credits-left": "795",
    })

    assert result.credits_used == 5
    assert result.credits_left == 795
    assert result.low_credits is False
    assert result.information_available is True


def test_low_credit_warning():
    result = parse_credit_headers({
        "api-credits-left": "10",
    })

    assert result.low_credits is True


def test_missing_headers():
    result = parse_credit_headers({})

    assert result.credits_used is None
    assert result.credits_left is None
    assert result.information_available is False


def test_invalid_header_values():
    result = parse_credit_headers({
        "api-credits-used": "invalid",
        "api-credits-left": "-10",
    })

    assert result.credits_used is None
    assert result.credits_left is None


def test_case_insensitive_headers():
    result = parse_credit_headers({
        "API-CREDITS-USED": "3",
        "API-CREDITS-LEFT": "50",
    })

    assert result.credits_used == 3
    assert result.credits_left == 50


@pytest.mark.parametrize("minimum", [-1, True, 1.5])
def test_invalid_minimum_remaining(minimum):
    with pytest.raises(ValueError):
        parse_credit_headers(
            {},
            minimum_remaining=minimum,
        )
