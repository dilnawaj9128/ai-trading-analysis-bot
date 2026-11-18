from types import SimpleNamespace

from market_data.mock_refresh_coordinator import (
    execute_mock_refresh,
)


REQUEST_ID = "a" * 32
TIMESTAMP = "2026-11-18T10:00:00+00:00"


def inputs():
    return {
        "approved": True,
        "cooldown_satisfied": True,
        "budget_available": True,
        "request_id": REQUEST_ID,
        "reservation": {
            "status": "PENDING",
            "credits": 1,
            "authorized_at": TIMESTAMP,
        },
        "journal_transaction": {
            "status": "FINALIZED",
            "credits": 1,
            "authorized_at": TIMESTAMP,
        },
        "response_callback": lambda: SimpleNamespace(
            status_code=200,
            headers={
                "api-credits-used": "1",
                "api-credits-left": "7",
            },
        ),
    }


def test_valid_mock_response():
    result = execute_mock_refresh(**inputs())
    assert result.status == "VALIDATED_OFFLINE"
    assert result.credits_left == 7


def test_missing_approval_blocks_callback():
    data = inputs()
    data["approved"] = False
    data["response_callback"] = lambda: 1 / 0

    result = execute_mock_refresh(**data)
    assert result.status == "BLOCKED"


def test_cooldown_blocks():
    data = inputs()
    data["cooldown_satisfied"] = False

    assert execute_mock_refresh(**data).status == "BLOCKED"


def test_budget_blocks():
    data = inputs()
    data["budget_available"] = False

    assert execute_mock_refresh(**data).status == "BLOCKED"


def test_timeout_is_uncertain():
    data = inputs()

    def timeout():
        raise TimeoutError("Simulated timeout")

    data["response_callback"] = timeout

    assert execute_mock_refresh(**data).status == "UNCERTAIN"


def test_bad_headers_are_uncertain():
    data = inputs()
    data["response_callback"] = lambda: SimpleNamespace(
        status_code=200,
        headers={},
    )

    assert execute_mock_refresh(**data).status == "UNCERTAIN"


def test_http_error_is_uncertain():
    data = inputs()
    data["response_callback"] = lambda: SimpleNamespace(
        status_code=429,
        headers={},
    )

    assert execute_mock_refresh(**data).status == "UNCERTAIN"
