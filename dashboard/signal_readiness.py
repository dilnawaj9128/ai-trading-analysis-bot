"""Conservative, offline signal-readiness assessment for dashboard display.

This module never contacts a provider and never generates UP/DOWN signals.
A separate reviewed integration must establish authenticated feed provenance,
quality, completed-candle semantics and strategy inputs before direction is shown.
"""


def assess_signal_readiness(
    *,
    expiry_minutes,
    stale,
    gaps,
    fetch_status,
    provider_feed_verified=False,
    broker_feed_verified=False,
    feed_mode="unknown",
    quality_status="UNKNOWN",
    completed_candles=0,
):
    if type(expiry_minutes) is not int or expiry_minutes not in (1, 5, 15):
        raise ValueError("Expiry must be 1, 5 or 15 minutes")

    reasons = []
    if fetch_status != "SUCCESS":
        reasons.append("No newly successful fetch; cached data is for observation only.")
    if stale is not False:
        reasons.append("Completed candle data is stale or freshness is unknown.")
    if type(gaps) is not int or gaps != 0:
        reasons.append("Data contains timestamp gaps or gap count is unknown.")
    if type(completed_candles) is not int or completed_candles < 60:
        reasons.append("At least 60 completed candles are required for research analysis.")
    if provider_feed_verified is not True:
        reasons.append("Provider feed provenance has not been verified.")
    if broker_feed_verified is not True:
        reasons.append("Selected broker's candles are not verified against provider candles.")
    if str(feed_mode).lower() not in ("live", "delayed"):
        reasons.append("Provider feed mode is unknown or unsupported.")
    if str(quality_status).upper() != "VALID":
        reasons.append("Data quality has not been independently marked VALID.")

    # A green readiness state must not silently become a trading signal.
    if not reasons:
        reasons.append(
            "All preliminary gates passed, but signal input mapping and "
            "platform comparison still require a separate review."
        )

    return {
        "signal": "NO TRADE",
        "expiry_minutes": expiry_minutes,
        "reasons": reasons,
        "analysis_only": True,
        "execution_enabled": False,
    }
