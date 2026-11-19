from market_data.basic8_credit_policy import PROVIDER_RESERVE_CREDITS
"""Read-only market data readiness report. No HTTP requests."""

from datetime import datetime, timezone

from market_data.provider_credit_state import load_credit_state
from market_data.pre_request_credit_gate import check_before_request
from market_data.provider_credit_guard import ProviderCreditStatusUnknown, ProviderCreditLimitReached


def main():
    now = datetime.now(timezone.utc)

    print("=== MARKET DATA READINESS ===")

    snapshot = load_credit_state(now=now)

    if snapshot is None:
        print("Provider status: UNKNOWN")
        print("Credit snapshot: MISSING OR EXPIRED")
        print("Live fetching: BLOCKED")
        print("Signal: NO TRADE")
        return

    print("Credits remaining:", snapshot.credits_left)
    print("Low credits:", snapshot.low_credits)

    try:
        decision = check_before_request(
            now=now,
            required_credits=1,
            reserve_credits=PROVIDER_RESERVE_CREDITS,
        )
    except ProviderCreditStatusUnknown:
        print("Live fetching: BLOCKED")
        print("Reason: Provider credit status unknown")
        print("Signal: NO TRADE")
        return
    except ProviderCreditLimitReached:
        print("Live fetching: BLOCKED")
        print("Reason: Insufficient credits above configured reserve")
        print("Signal: NO TRADE")
        return

    if decision.allowed:
        print("Credit gate: PASSED")
        print("Other authorization checks: NOT EVALUATED")
        print("Live fetching: NOT AUTHORIZED BY THIS REPORT")
    else:
        print("Credit gate: BLOCKED")
        print("Reason: Insufficient credits above reserve")
        print("Signal: NO TRADE")

    print("No HTTP requests performed.")


if __name__ == "__main__":
    main()
