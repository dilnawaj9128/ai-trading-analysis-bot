import os
import json
import time
from pathlib import Path
from datetime import datetime, timezone, timedelta

from dotenv import load_dotenv

from scripts.run_15m_forward_collection import eligibility
from scripts.run_15m_forward_collection import main as collect
from scripts.recover_credit_blockers_once import run as recover
from scripts.run_accuracy_all import archive_settlement_pass

load_dotenv(dotenv_path=Path.cwd() / ".env")

def show(data):
    print(json.dumps(data, indent=2, default=str), flush=True)

def main():
    print("===== OFFLINE SETTLEMENT =====")
    show(archive_settlement_pass())

    state = eligibility()
    show(state)

    allowed = {
        "15_MINUTE_NONOVERLAP_WINDOW",
        "PROVIDER_CANDLE_LAG_BUFFER",
        "UNCERTAIN_PROVIDER_REQUESTS_REQUIRE_RECONCILIATION",
        "CREDIT_RENEWAL_UNRESOLVED",
        "CREDIT_SNAPSHOT_STALE_OR_MISSING",
        "ACCOUNT_USAGE_BOOTSTRAP_UNRESOLVED",
    }

    if set(state["reasons"]) - allowed:
        print("SAFE STOP: Unexpected blocker")
        return 2

    next_time = state.get("next_eligible_utc")

    if next_time:
        target = datetime.fromisoformat(next_time)
        target += timedelta(minutes=2)
        wait = (target - datetime.now(timezone.utc)).total_seconds()

        if wait > 0:
            print("Waiting seconds:", int(wait), flush=True)
            time.sleep(wait)

    print("===== CREDIT RECOVERY =====")

    result = recover(
        approved=True,
        api_key=os.getenv("TWELVE_DATA_API_KEY")
    )
    show(result)

    if not result["status"].startswith("FRESH_OPERATIONAL"):
        print("SAFE STOP: Credit recovery incomplete")
        return 2

    state = eligibility()

    if state["status"] != "PRECHECK_ONLY_EXISTING_REQUEST_GUARD_STILL_REQUIRED":
        show(state)
        print("SAFE STOP: Eligibility blocked")
        return 2

    print("===== GUARDED DATA CAPTURE =====")
    code = collect(["--one-authorized-capture"])

    if code != 0:
        print("SAFE STOP: No automatic retry")
        return 2

    print("===== FINAL SETTLEMENT =====")
    show(archive_settlement_pass())

    print("===== FINAL READINESS =====")
    show(eligibility())

    return 0

if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print("SAFE STOP:", type(exc).__name__)
        raise SystemExit(2)
