from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from threading import Barrier

from market_data.api_credit_monitor import CreditSnapshot
from market_data.provider_credit_state import save_credit_state
from market_data.unified_request_guard import authorize_request


NOW = datetime(2026, 11, 13, 12, 0, tzinfo=timezone.utc)


def test_concurrent_requests_cannot_reuse_last_credit(tmp_path):
    provider_path = tmp_path / "provider.json"
    budget_path = tmp_path / "budget.json"

    save_credit_state(
        CreditSnapshot(
            credits_used=0,
            credits_left=21,
            low_credits=False,
            information_available=True,
        ),
        path=provider_path,
        now=NOW,
    )

    barrier = Barrier(2)

    def attempt():
        barrier.wait()

        try:
            authorize_request(
                provider_state_path=provider_path,
                local_budget_path=budget_path,
                now=NOW,
            )
            return "AUTHORIZED"
        except Exception:
            return "BLOCKED"

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: attempt(), range(2)))

    assert results.count("AUTHORIZED") == 1
    assert results.count("BLOCKED") == 1
