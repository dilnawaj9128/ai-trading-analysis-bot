from datetime import datetime, timezone
from unittest.mock import Mock

from market_data.credit_response_handler import (
    refresh_credits_from_response,
)
from market_data.provider_credit_state import load_credit_state


NOW = datetime(2026, 11, 13, 12, 0, tzinfo=timezone.utc)


def test_valid_response_updates_state(tmp_path):
    response = Mock()
    response.headers = {
        "api-credits-used": "5",
        "api-credits-left": "95",
    }

    path = tmp_path / "credits.json"

    result = refresh_credits_from_response(
        response,
        path=path,
        now=NOW,
    )

    assert result.updated is True
    assert result.credits_left == 95

    saved = load_credit_state(path=path, now=NOW)
    assert saved.credits_left == 95


def test_missing_headers_does_not_create_state(tmp_path):
    response = Mock()
    response.headers = {}

    path = tmp_path / "credits.json"

    result = refresh_credits_from_response(
        response,
        path=path,
        now=NOW,
    )

    assert result.updated is False
    assert not path.exists()


def test_used_only_does_not_create_state(tmp_path):
    response = Mock()
    response.headers = {
        "api-credits-used": "5",
    }

    path = tmp_path / "credits.json"

    result = refresh_credits_from_response(
        response,
        path=path,
        now=NOW,
    )

    assert result.updated is False
    assert not path.exists()


def test_invalid_headers_are_ignored(tmp_path):
    response = Mock()
    response.headers = Mock()

    path = tmp_path / "credits.json"

    result = refresh_credits_from_response(
        response,
        path=path,
        now=NOW,
    )

    assert result.updated is False
    assert not path.exists()


def test_zero_remaining_credits_saved(tmp_path):
    response = Mock()
    response.headers = {
        "api-credits-left": "0",
    }

    path = tmp_path / "credits.json"

    result = refresh_credits_from_response(
        response,
        path=path,
        now=NOW,
    )

    assert result.updated is True

    saved = load_credit_state(path=path, now=NOW)
    assert saved.credits_left == 0


def test_invalid_credit_value_not_saved(tmp_path):
    response = Mock()
    response.headers = {
        "api-credits-left": "invalid",
    }

    path = tmp_path / "credits.json"

    result = refresh_credits_from_response(
        response,
        path=path,
        now=NOW,
    )

    assert result.updated is False
    assert not path.exists()
