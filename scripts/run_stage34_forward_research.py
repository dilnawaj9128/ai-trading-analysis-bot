"""Stage 34 safe forward research inspection and optional synthetic demonstration.

No API requests, no broker orders, and no auto-settlement of legacy journals.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

from research.stage34_forward_settlement import settle_observation, summarize_outcomes


def inspect_journal(path: Path):
    if not path.exists():
        print("No forward journal found. Nothing settled.")
        return
    entries = [json.loads(line) for line in path.read_text(encoding="utf8").splitlines() if line.strip()]
    blocked = sum(e.get("status") == "BLOCKED" for e in entries)
    eligible = sum(e.get("status") == "VALID" and e.get("signal") in ("UP", "DOWN") for e in entries)
    print("STAGE 34 READ-ONLY FORWARD JOURNAL CHECK")
    print("records:", len(entries))
    print("blocked:", blocked)
    print("directional_observations:", eligible)
    print("settled_by_this_command: 0")
    print("Unverified existing observations remain NOT_EVALUATED.")
    print("No live provider or broker outcome inferred.")


def demonstration():
    t = datetime(2026, 11, 19, 12, 0, tzinfo=timezone.utc)
    obs = {"status": "VALID", "signal": "UP",
           "analysis_only": True, "execution_enabled": False,
           "expiry_minutes": 15, "timeframe": "1min",
           "observed_at_utc": t.isoformat(), "signal_time_utc": t.isoformat(),
           "entry_reference_close": 1.10}
    dates = pd.date_range(t + timedelta(minutes=1), periods=14, freq="min", tz="UTC")
    frame = pd.DataFrame({
        "timestamp": dates, "Open": [1.10] * 14,
        "High": [1.12] * 14, "Low": [1.09] * 14,
        "Close": [1.10] * 13 + [1.11],
    })
    r = settle_observation(obs, frame, received_at=t + timedelta(minutes=16), simulated=True)
    print("STAGE 34 SYNTHETIC DEMONSTRATION (NOT ACTUAL TRADING)")
    print("result:", r["result"])
    print("status:", r["status"])
    print("pnl_units:", r["pnl_units"])
    print("summary:", summarize_outcomes([r]))
    print("No request, real money, or broker parity.")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--journal", default="data/forward_testing/stage32_observations.jsonl")
    p.add_argument("--demo", action="store_true", help="Synthetic-only demonstration")
    args = p.parse_args()
    if args.demo:
        demonstration()
    else:
        inspect_journal(Path(args.journal))


if __name__ == "__main__":
    main()
