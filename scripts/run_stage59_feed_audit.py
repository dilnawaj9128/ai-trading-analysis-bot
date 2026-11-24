"""Stage 59 offline EUR/USD candle comparison (no broker login, HTTP or orders).

Compare completed 1-minute UTC candles from a saved Twelve Data capture with
a user-supplied Quotex CSV. This is a DESCRIPTIVE comparison only. CSV contents,
even if identical, cannot independently prove Quotex source authenticity,
platform feed parity, live trading suitability, or predictive accuracy.

Expected broker CSV columns (case-insensitive):
 timestamp,Open,High,Low,Close
 Timestamp must include a timezone, e.g. 2026-11-24T14:00:00Z.
 No implied UTC for timezone-naive broker data. Never use unfinished candles.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from datetime import datetime, timedelta, timezone
from pathlib import Path
from statistics import median

DEFAULT_PROVIDER = Path("data/real_market/stage52d_new_completed.csv")
DEFAULT_BROKER = Path("data/broker/quotex_eurusd_1m.csv")
REQUIRED = ("timestamp", "open", "high", "low", "close")


class FeedComparisonError(ValueError):
    pass


def _timestamp(value):
    try:
        t = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except (TypeError, ValueError) as exc:
        raise FeedComparisonError("Invalid candle timestamp") from exc
    if t.tzinfo is None or t.utcoffset() is None:
        raise FeedComparisonError(
            "Candle timestamps must carry an explicit UTC offset; never assume timezone"
        )
    t = t.astimezone(timezone.utc)
    if t.second != 0 or t.microsecond != 0:
        raise FeedComparisonError("Expected exact one-minute candle-open timestamps")
    return t


def load_candles(path, *, now=None):
    """Return timestamp-keyed validated completed one-minute candles."""
    path = Path(path)
    if not path.is_file() or path.is_symlink():
        raise FeedComparisonError("CSV missing or redirected: " + str(path))
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None or now.utcoffset() is None:
        raise FeedComparisonError("Timezone-aware clock required")
    now = now.astimezone(timezone.utc)
    try:
        with path.open("r", newline="", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            if not reader.fieldnames:
                raise FeedComparisonError("CSV missing header")
            header = [s.strip().lower() for s in reader.fieldnames]
            if len(header) != len(set(header)):
                raise FeedComparisonError("Duplicate CSV headers")
            if not set(REQUIRED).issubset(set(header)):
                raise FeedComparisonError("CSV needs timestamp,Open,High,Low,Close")
            mapping = dict(zip(header, reader.fieldnames))
            records = {}
            previous = None
            gaps = 0
            for original in reader:
                timestamp = _timestamp(original[mapping["timestamp"]])
                if timestamp + timedelta(minutes=1) > now:
                    raise FeedComparisonError("Future or incomplete candle present")
                if previous is not None:
                    if timestamp <= previous:
                        raise FeedComparisonError("Nonchronological or duplicate candles")
                    if timestamp - previous != timedelta(minutes=1):
                        gaps += 1
                prices = []
                for key in ("open", "high", "low", "close"):
                    try:
                        price = float(original[mapping[key]])
                    except (ValueError, TypeError, KeyError) as exc:
                        raise FeedComparisonError("Non-numeric OHLC") from exc
                    if not math.isfinite(price) or price <= 0:
                        raise FeedComparisonError("Non-positive or nonfinite OHLC")
                    prices.append(price)
                op, hi, lo, cl = prices
                if not lo <= min(op, cl) <= max(op, cl) <= hi:
                    raise FeedComparisonError("Invalid OHLC high/low relationship")
                records[timestamp] = (op, hi, lo, cl)
                previous = timestamp
    except (OSError, UnicodeError, csv.Error) as exc:
        raise FeedComparisonError("CSV unreadable") from exc
    if not records:
        raise FeedComparisonError("No completed candles")
    return {"rows": records, "gaps": gaps, "latest_utc": previous.isoformat()}


def recovery_capture_attestation(provider_csv, *, journal=None, old_probe=None):
    """Correlate local recovery capture with request-bound verified evidence."""
    provider_csv = Path(provider_csv)
    root = Path("data/api_usage")
    journal = Path(journal) if journal is not None else root / "stage52d_new_recovery_probe.json"
    old_probe = Path(old_probe) if old_probe is not None else root / "approved_research_probe.json"
    try:
        evidence = json.loads(journal.read_text(encoding="utf-8"))
        if (type(evidence) is not dict or evidence.get("version") != 1
                or evidence.get("status") != "VERIFIED"
                or evidence.get("checkpoint") != "VERIFIED"
                or evidence.get("http_attempted") is not True
                or evidence.get("analysis_only") is not True
                or evidence.get("trading_enabled") is not False
                or Path(evidence.get("csv_path", "")).resolve() != provider_csv.resolve()
                or hashlib.sha256(provider_csv.read_bytes()).hexdigest()
                    != evidence.get("csv_sha256")):
            return False
        from market_data.recovery_verified_gate import verified_recovery_override
        return verified_recovery_override(old_probe) is True
    except (OSError, UnicodeError, ValueError, TypeError, KeyError, ImportError):
        return False


def compare(provider_csv=DEFAULT_PROVIDER, broker_csv=DEFAULT_BROKER,
            *, broker_market="unknown", now=None, max_close_diff_pips=1.0,
            provider_attested=None):
    """Produce a non-trading report. An apparent match NEVER unlocks signals."""
    broker_market = str(broker_market).strip().lower()
    if broker_market not in {"regular", "otc", "unknown"}:
        raise FeedComparisonError("Broker market must be regular, otc or unknown")
    if (not math.isfinite(max_close_diff_pips) or max_close_diff_pips < 0):
        raise FeedComparisonError("Invalid comparison tolerance")

    provider_csv, broker_csv = Path(provider_csv), Path(broker_csv)
    result = {
        "stage": 59, "mode": "READ_ONLY_CANDLE_COMPARISON",
        "provider": "Twelve Data EUR/USD forex",
        "broker": "Quotex EUR/USD", "broker_market": broker_market.upper(),
        "provider_csv": str(provider_csv), "broker_csv": str(broker_csv),
        "status": "UNVERIFIED", "matched_candles": 0,
        "provider_capture_attested": False, "broker_source_independently_attested": False,
        "broker_parity_verified": False, "prediction_accuracy_verified": False,
        "live_signal": "NO TRADE", "expiry_minutes": 15,
        "no_http_requests": True, "broker_orders": 0,
    }
    if not provider_csv.is_file():
        result["reason"] = "PROVIDER_CSV_MISSING: earlier in-memory fetch was not persisted as a CSV"
        return result
    provider = load_candles(provider_csv, now=now)
    result["provider_rows"] = len(provider["rows"])
    result["provider_gaps"] = provider["gaps"]
    result["provider_latest_utc"] = provider["latest_utc"]
    attested = (recovery_capture_attestation(provider_csv)
                if provider_attested is None else bool(provider_attested))
    result["provider_capture_attested"] = attested

    if not broker_csv.is_file():
        result["reason"] = (
            "BROKER_CSV_MISSING: export genuine Quotex EUR/USD M1 candles "
            "with timezone-aware timestamps to the requested path"
        )
        return result

    broker = load_candles(broker_csv, now=now)
    result["broker_rows"] = len(broker["rows"])
    result["broker_gaps"] = broker["gaps"]
    result["broker_latest_utc"] = broker["latest_utc"]
    shared = sorted(set(provider["rows"]) & set(broker["rows"]))
    result["matched_candles"] = len(shared)
    result["provider_only_candles"] = len(provider["rows"]) - len(shared)
    result["broker_only_candles"] = len(broker["rows"]) - len(shared)

    if shared:
        # EUR/USD: 1 pip = 0.0001. Descriptive differences are not parity proof.
        close_diffs = [
            abs(provider["rows"][t][3] - broker["rows"][t][3]) * 10000
            for t in shared
        ]
        direction_mismatch = sum(
            (provider["rows"][t][3] > provider["rows"][t][0])
            != (broker["rows"][t][3] > broker["rows"][t][0])
            for t in shared
        )
        result.update({
            "overlap_first_utc": shared[0].isoformat(),
            "overlap_last_utc": shared[-1].isoformat(),
            "median_close_difference_pips": round(median(close_diffs), 5),
            "max_close_difference_pips": round(max(close_diffs), 5),
            "within_tolerance_candles": sum(
                d <= max_close_diff_pips for d in close_diffs
            ),
            "tolerance_pips": max_close_diff_pips,
            "up_down_direction_mismatches": direction_mismatch,
        })

    if broker_market == "otc":
        result["reason"] = (
            "OTC_MARKET: composite regular-forex and broker OTC are not "
            "assumed to share a candle-generating feed; no parity authorization"
        )
    elif broker_market == "unknown":
        result["reason"] = "BROKER_MARKET_UNCLASSIFIED: select regular or otc"
    elif len(shared) < 60:
        result["reason"] = "INSUFFICIENT_EXACT_UTC_OVERLAP: minimum 60 one-minute candles"
    elif provider["gaps"] or broker["gaps"]:
        result["reason"] = "CANDLE_GAPS_DETECTED"
    elif not attested:
        result["reason"] = "PROVIDER_CAPTURE_UNATTESTED"
    elif result["within_tolerance_candles"] != len(shared):
        result["reason"] = "OBSERVED_CLOSE_PRICES_DIVERGE"
    else:
        result["status"] = "DESCRIPTIVE_MATCH_ONLY"
        result["reason"] = (
            "Observed CSV similarity is not independent broker source "
            "authentication or ongoing live feed parity"
        )

    return result


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--provider-csv", type=Path, default=DEFAULT_PROVIDER)
    ap.add_argument("--broker-csv", type=Path, default=DEFAULT_BROKER)
    ap.add_argument("--broker-market", choices=["regular", "otc", "unknown"], default="unknown")
    ap.add_argument("--max-close-diff-pips", type=float, default=1.0)
    args = ap.parse_args(argv)
    try:
        report = compare(
            args.provider_csv, args.broker_csv, broker_market=args.broker_market,
            max_close_diff_pips=args.max_close_diff_pips,
        )
        print(json.dumps(report, indent=2, sort_keys=True))
        print("No HTTP. No API credits. No broker orders. Live trading signal: NO TRADE.")
        return 0
    except (FeedComparisonError, OSError) as exc:
        print(json.dumps({
            "stage": 59, "status": "INVALID_EVIDENCE",
            "reason": str(exc), "broker_parity_verified": False,
            "live_signal": "NO TRADE", "no_http_requests": True, "broker_orders": 0,
        }, indent=2))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
