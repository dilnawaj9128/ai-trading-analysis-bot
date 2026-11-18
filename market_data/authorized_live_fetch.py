"""Authorized Twelve Data live research fetch. No broker execution."""

import os
from datetime import timezone

import requests

from config.market_config import create_research_config
from market_data import twelve_data_client as td
from market_data.authorization_ledger import transition_authorization
from market_data.credit_response_handler import refresh_credits_from_response
from market_data.provider_credit_state import DEFAULT_PATH
from market_data.unified_request_guard import authorize_request
from market_data.basic8_credit_policy import PROVIDER_RESERVE_CREDITS


def fetch_authorized_live_candles(
    config,
    *,
    api_key=None,
    state_path=td.STATE_PATH,
    provider_credit_path=DEFAULT_PATH,
    now=None,
    session=None,
):
    """Validate, authorize once, fetch once, and preserve reservation evidence."""

    validated = create_research_config(
        config.platform,
        config.market,
        config.symbol,
        config.timeframe,
        config.expiry_minutes,
    )
    if config != validated:
        raise td.MarketDataError("Unsafe or modified research config")

    key = api_key if api_key is not None else os.environ.get(
        "TWELVE_DATA_API_KEY"
    )
    if not key:
        raise td.MarketDataError("TWELVE_DATA_API_KEY is missing")

    now = now if now is not None else td.utc_now()
    if now.tzinfo is None:
        raise td.MarketDataError("Current time must have a timezone")
    now = now.astimezone(timezone.utc)

    # This call already reserves the local request budget.
    authorization = authorize_request(
        provider_state_path=provider_credit_path,
        local_budget_path=state_path,
        now=now,
        reserve_credits=PROVIDER_RESERVE_CREDITS,
    )

    if (
        not authorization.authorized
        or not authorization.local_budget_reserved
        or not authorization.request_id
    ):
        raise td.MarketDataError("Incomplete request authorization")

    client = session if session is not None else requests

    try:
        response = client.get(
            td.API_URL,
            params={
                "symbol": config.symbol,
                "interval": config.timeframe,
                "outputsize": td.MAX_CANDLES,
                "timezone": "UTC",
                "apikey": key,
                "format": "JSON",
            },
            timeout=td.TIMEOUT_SECONDS,
        )

        response.raise_for_status()
        payload = response.json()
        result = td.parse_candles(payload, config, now=now)

        # A response snapshot does not settle this reservation.
        refresh = refresh_credits_from_response(
            response,
            path=provider_credit_path,
            now=now,
        )

        if refresh.updated is not True:
            raise td.MarketDataError(
                "Provider credit reconciliation unavailable; "
                "reservation retained"
            )

        return result

    except Exception as exc:
        # Keep credits reserved after an uncertain request outcome.
        try:
            transition_authorization(
                provider_state_path=provider_credit_path,
                request_id=authorization.request_id,
                status="UNCERTAIN",
            )
        except Exception as ledger_exc:
            raise td.MarketDataError(
                "Live fetch failed and reservation status "
                "could not be recorded; manual review required"
            ) from ledger_exc

        if isinstance(exc, td.MarketDataError):
            raise

        raise td.MarketDataError(
            "Authorized live fetch failed; reservation retained"
        ) from exc
