"""Stage 33: offline verification of an approved provider probe's local evidence.

This checks provenance *within the local trusted workflow*, not that a file
is authentic against an adversary who can rewrite both CSV and journal.
It does not call an API, verify Quotex quote parity, or enable orders.
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from research.stage32_forward_safety import assess_snapshot


def evaluate_attested_snapshot(csv_path, journal_path, *, observed_at=None):
    def blocked(reason):
        return {"signal": "NO TRADE", "status": "BLOCKED",
                "reason": reason, "provider_attested": False,
                "analysis_only": True, "execution_enabled": False}

    try:
        now = pd.Timestamp(observed_at if observed_at is not None else datetime.now(timezone.utc))
        if now.tzinfo is None:
            return blocked("Observation timestamp timezone required")
        now = now.tz_convert("UTC")
        csv_path = Path(csv_path).resolve()
        journal_path = Path(journal_path)
        journal = json.loads(journal_path.read_text(encoding="utf8"))
        if type(journal) is not dict or journal.get("version") != 1:
            return blocked("Invalid probe journal")
        attempts = journal.get("attempts")
        if type(attempts) is not list or not attempts:
            return blocked("Missing probe verification")
        # Do not trust older verified attempts when latest is unresolved.
        attempt = attempts[-1]
        if type(attempt) is not dict or attempt.get("status") != "VERIFIED":
            return blocked("Latest provider attempt unresolved")
        digest = attempt.get("csv_sha256")
        if not isinstance(digest, str) or re.fullmatch(r"[0-9a-f]{64}", digest) is None:
            return blocked("Missing hashed provenance: re-attestation required")
        if attempt.get("provider") != "twelve_data" or attempt.get("symbol") != "EUR/USD" or attempt.get("timeframe") != "1min":
            return blocked("Provider metadata mismatch")
        if attempt.get("csv_path") != str(csv_path):
            return blocked("Attested CSV path mismatch")
        verified = pd.Timestamp(attempt["verified_at_utc"])
        if verified.tzinfo is None:
            return blocked("Verification timestamp timezone missing")
        verified = verified.tz_convert("UTC")
        if verified > now:
            return blocked("Verification timestamp in future")
        # The latest file is a snapshot, not a durable guarantee of realtime data.
        if (now - verified).total_seconds() > 180:
            return blocked("Provider attestation stale")
        raw_bytes = csv_path.read_bytes()
        if hashlib.sha256(raw_bytes).hexdigest() != digest:
            return blocked("CSV content changed since provider verification")
        candles = pd.read_csv(csv_path)
        if len(candles) != attempt.get("candles"):
            return blocked("Attested candle count mismatch")
        # A successful provider probe certifies the response came through
        # the configured Twelve Data workflow, NOT that it is an undelayed
        # live feed. Feed mode remains unverified until separately attested.
        evaluated = assess_snapshot(candles, observed_at=now,
                                    source_verified=True, feed_mode="unknown",
                                    symbol="EUR/USD", timeframe="1min")
        evaluated.update(provider_attested=True, analysis_only=True,
                         execution_enabled=False)
        # Never override the NO TRADE gate with a fabricated feed mode.
        return evaluated
    except (OSError, ValueError, KeyError, TypeError, OverflowError, pd.errors.ParserError) as exc:
        return blocked("Attestation invalid or unavailable: " + type(exc).__name__)
