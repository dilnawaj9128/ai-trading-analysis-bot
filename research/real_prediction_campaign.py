"""Evidence-first EUR/USD 15-minute research campaign.

Never sends HTTP, places orders or certifies broker-feed parity.  History
remains exploratory; only decisions timestamped and immutably recorded before
settlement may enter the prospective scorecard.
"""
from __future__ import annotations

import hashlib
import fcntl
import json
import math
import os
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

EXPIRY = timedelta(minutes=15)
ONE_MINUTE = timedelta(minutes=1)


def utc(value):
    if isinstance(value, datetime):
        dt = value
    else:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if dt.tzinfo is None or dt.utcoffset() is None:
        raise ValueError("A timezone-aware UTC timestamp is required")
    return dt.astimezone(timezone.utc)


def canonical(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def digest(obj):
    return hashlib.sha256(canonical(obj)).hexdigest()


def _new_file(path, record):
    """Atomic, exclusive, immutable publication. Existing audit files never changed."""
    path = Path(path)
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    body = canonical(record) + b"\n"
    temp = None
    try:
        with tempfile.NamedTemporaryFile(mode="wb", dir=path.parent, prefix=".pred_", delete=False) as h:
            temp = Path(h.name)
            os.fchmod(h.fileno(), 0o600)
            h.write(body)
            h.flush()
            os.fsync(h.fileno())
        os.link(temp, path)  # fail without overwriting if another process got here first
        dirfd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(dirfd)
        finally:
            os.close(dirfd)
    finally:
        if temp is not None:
            temp.unlink(missing_ok=True)


def _load_envelope(path, expected_type):
    doc = json.loads(Path(path).read_text(encoding="utf-8"))
    if type(doc) is not dict or doc.get("schema_version") != 1 or doc.get("kind") != expected_type:
        raise ValueError("Unknown prospective evidence schema")
    record = doc.get("record")
    if type(record) is not dict or doc.get("sha256") != digest(record):
        raise ValueError("Prospective evidence checksum invalid")
    return record


def _envelope(kind, record):
    return {"schema_version": 1, "kind": kind, "record": record, "sha256": digest(record)}


def _candles(path):
    from research.stage29_backtest import load_candles
    from scripts.run_stage45_dataset_audit import parse_candles, quality
    src = Path(path)
    data = load_candles(src)
    q = quality(parse_candles(src))
    if not q["continuous_one_minute_candles"] or len(data) < 90:
        raise ValueError("Minimum 90 validated contiguous completed candles required")
    return src, data, q


def historical_dataset(path, payout=0.80):
    """Run the existing Stage 55/56 algorithms without choosing new thresholds."""
    from scripts.run_stage55_robust_validation import build_report
    from scripts.stage56_failure_analysis import build_failure_report
    base = build_report(path, min_nonpush=100, payout=payout)
    fail = build_failure_report(path, payout=payout)
    audit = base["stage55"]["statistical_audit"]
    if audit is None:
        raise ValueError("No historical holdout audit")
    h = fail["holdout"]
    if (h["wins"], h["losses"], h["pushes"]) != (audit["wins"], audit["losses"], audit["pushes"]):
        raise ValueError("Stage 55/56 disagreement about holdout outcomes")
    events = fail.get("events", [])
    if len(events) != h["wins"] + h["losses"] + h["pushes"]:
        raise ValueError("Holdout events missing")
    # Never average distinct dataset win rates; these are historical, already inspected.
    return {
        "dataset": str(path), "source_sha256": base["source_sha256"],
        "rows": base["quality"]["rows"],
        "first_candle_utc": base["quality"]["first_close_utc"],
        "last_candle_utc": base["quality"]["last_close_utc"],
        "wins": h["wins"], "losses": h["losses"], "pushes": h["pushes"],
        "nonpush": h["nonpush"],
        "win_rate": audit["observed_nonpush_win_rate"],
        "net_units": h["idealized_net_units"],
        "wilson_95pct": audit["wilson_95pct_nonpush_win_rate"],
        "pvalue_vs_breakeven": audit["one_sided_exact_pvalue_vs_break_even"],
        "break_even_win_rate": audit["break_even_nonpush_win_rate_at_payout"],
        "holdout_first_entry_utc": events[0]["entry_utc"] if events else None,
        "holdout_last_expiry_utc": events[-1]["exit_utc"] if events else None,
        "status": audit["status"], "already_inspected": True,
        "walk_forward": base.get("walk_forward", {"status": "NOT_EVALUATED"}),
        "failure_groups_descriptive_only": fail.get("groups", {}),
        "training_baseline": base.get("stage29", {}).get("training"),
        "research_only": True,
    }


def historical_campaign(paths, payout=0.80):
    if not paths:
        raise ValueError("At least one saved historical candle CSV is required")
    datasets, rejected = [], []
    seen_hashes = set()
    for p in paths:
        try:
            item = historical_dataset(p, payout=payout)
            if item["source_sha256"] in seen_hashes:
                raise ValueError("Duplicate dataset SHA256 — would double count")
            seen_hashes.add(item["source_sha256"])
            datasets.append(item)
        except (OSError, ValueError, KeyError, TypeError, ImportError, AssertionError) as exc:
            rejected.append({"path": str(p), "error": type(exc).__name__, "reason": str(exc)})
    overlap = []
    sorted_items = sorted(datasets, key=lambda x: x["first_candle_utc"])
    for a, b in zip(sorted_items, sorted_items[1:]):
        if a["last_candle_utc"] >= b["first_candle_utc"]:
            overlap.append([a["dataset"], b["dataset"]])
    # All historical periods were previously inspected: not independent proof.
    count = sum(x["nonpush"] for x in datasets)
    wins = sum(x["wins"] for x in datasets)
    losses = sum(x["losses"] for x in datasets)
    return {
        "schema_version": 1, "mode": "HISTORICAL_EXPLORATORY",
        "source": "existing Stage 29/55/56 research code",
        "datasets": datasets, "rejected_datasets": rejected,
        "overlapping_candle_ranges": overlap,
        "overall_descriptive_only": {
            "nonpush": count, "wins": wins, "losses": losses,
            "win_rate": wins / count if count else None,
            "net_units": round(sum(x["net_units"] for x in datasets), 8),
            "safe_to_pool_as_independent": False,
            "reason": "Historical datasets already inspected; duplicate/overlap and dependence possible",
        },
        "prediction_accuracy_verified": False,
        "live_signal": "NO TRADE", "no_http_requests": True, "broker_orders": 0,
    }



def preflight_observation_window(journal, *, now=None):
    """Fail closed before spending API credits if a 15-minute window is occupied.

    Read-only; final locking/nonoverlap check still happens inside observe().
    This cannot guarantee a new candle or replace provider authorization.
    """
    now = utc(now or datetime.now(timezone.utc))
    directory = Path(journal) / "observations"
    if not directory.exists():
        return {"eligible": True, "reason": "NO_PRIOR_OBSERVATION"}
    latest = None
    for path in directory.glob("*.json"):
        record = _load_envelope(path, "OBSERVATION")
        decision = utc(record["decision_time_utc"])
        recorded = utc(record["recorded_at_utc"])
        expiry = utc(record["expiry_time_utc"])
        if expiry != decision + EXPIRY or recorded >= expiry:
            raise ValueError("Invalid prospective observation timing")
        if decision > now or recorded > now:
            raise ValueError("Future-dated prospective observation")
        if latest is None or decision > latest:
            latest = decision
    if latest is not None and now < latest + EXPIRY:
        return {
            "eligible": False,
            "reason": "15_MINUTE_NONOVERLAP_WINDOW",
            "next_eligible_utc": (latest + EXPIRY).isoformat(),
        }
    return {"eligible": True, "reason": "WINDOW_AVAILABLE"}

def observe(path, *, journal, now=None, max_age_seconds=180):
    """Log a time-stamped research hypothesis BEFORE its 15m outcome exists.

    This is deliberately not the production broker signal. A research hypothesis
    can be UP/DOWN, while the tradable signal always remains NO TRADE.
    """
    from research.stage29_backtest import existing_strategy_on_prefix
    now = utc(now or datetime.now(timezone.utc))
    src, frame, q = _candles(path)
    latest_open = utc(frame["timestamp"].iloc[-1])
    completed_at = latest_open + ONE_MINUTE
    age = (now - completed_at).total_seconds()
    if not 0 <= age <= max_age_seconds:
        raise ValueError("Latest completed candle is future/incomplete or stale")
    research_hypothesis = existing_strategy_on_prefix(frame.copy())
    if research_hypothesis not in ("UP", "DOWN", "NO TRADE"):
        raise ValueError("Unexpected offline research hypothesis")
    record = {
        "symbol": "EUR/USD", "timeframe": "1min", "expiry_minutes": 15,
        "model": "existing_stage29_research_strategy_fixed",
        "recorded_at_utc": now.isoformat(),
        "last_candle_open_utc": latest_open.isoformat(),
        "decision_time_utc": completed_at.isoformat(),
        "expiry_time_utc": (completed_at + EXPIRY).isoformat(),
        "entry_reference_close": float(frame["Close"].iloc[-1]),
        "research_hypothesis": research_hypothesis,
        "live_trading_signal": "NO TRADE",
        "provider_csv_sha256": hashlib.sha256(src.read_bytes()).hexdigest(),
        "source_file": str(src),
        "data_rows": len(frame), "data_age_seconds_at_observation": age,
        "source_provenance": "LOCAL_CSV_UNATTESTED",
        "broker_parity_verified": False, "execution_enabled": False,
    }
    # Stable by timestamp/model, preventing duplicates across repeated invocations.
    key = hashlib.sha256((record["symbol"] + "|" + record["decision_time_utc"] + "|" + record["model"]).encode()).hexdigest()[:24]
    destination = Path(journal) / "observations" / (key + ".json")
    destination.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    lockpath = Path(journal) / ".observe.lock"
    with lockpath.open("a+b") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        for prior in destination.parent.glob("*.json"):
            previous = _load_envelope(prior, "OBSERVATION")
            previous_time = utc(previous["decision_time_utc"])
            if abs((completed_at - previous_time).total_seconds()) < EXPIRY.total_seconds():
                raise ValueError("15-minute non-overlap rule: a recent observation exists")
        _new_file(destination, _envelope("OBSERVATION", record))
    return destination, record


def settle_one(observation_path, later_csv, *, journal, now=None):
    """Only settle a prior immutable hypothesis using strictly later evidence."""
    observation_path = Path(observation_path)
    obs = _load_envelope(observation_path, "OBSERVATION")
    now = utc(now or datetime.now(timezone.utc))
    expiry = utc(obs["expiry_time_utc"])
    if now < expiry or now <= utc(obs["recorded_at_utc"]):
        raise ValueError("Outcome not observable yet")
    source, frame, quality = _candles(later_csv)
    # CSV candle timestamps are bar opens; settlement price is the close at expiry.
    target_open = expiry - ONE_MINUTE
    row = frame[frame["timestamp"] == target_open]
    if len(row) != 1:
        raise ValueError("Exact expiry candle absent; cannot infer or interpolate")
    if utc(frame["timestamp"].iloc[-1]) + ONE_MINUTE > now:
        raise ValueError("Settlement source contains an incomplete candle")
    # Source must include the observed candle at the same immutable entry close.
    origin_open = utc(obs["last_candle_open_utc"])
    orig = frame[frame["timestamp"] == origin_open]
    if len(orig) != 1 or not math.isclose(float(orig["Close"].iloc[0]), float(obs["entry_reference_close"]), abs_tol=1e-10, rel_tol=0):
        raise ValueError("Settlement provider data does not match original entry reference")
    hypo = obs["research_hypothesis"]
    exit_close = float(row["Close"].iloc[0])
    entry_close = float(obs["entry_reference_close"])
    if hypo == "NO TRADE":
        result = "ABSTAINED"
    elif exit_close == entry_close:
        result = "PUSH"
    elif (exit_close > entry_close) == (hypo == "UP"):
        result = "WIN"
    else:
        result = "LOSS"
    if utc(obs["recorded_at_utc"]) >= expiry:
        raise ValueError("Observation created after outcome")
    record = {
        "observation_filename": observation_path.name,
        "observation_sha256": digest(obs),
        "recorded_at_utc": now.isoformat(),
        "expiry_time_utc": expiry.isoformat(),
        "research_hypothesis": hypo, "result": result,
        "entry_reference_close": entry_close, "exit_reference_close": exit_close,
        "settlement_csv_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "settlement_source_file": str(source),
        "broker_parity_verified": False, "execution_enabled": False,
        "claim": "HYPOTHETICAL_PROVIDER_CANDLE_CLOSE_ONLY",
    }
    target = Path(journal) / "settlements" / observation_path.name
    _new_file(target, _envelope("SETTLEMENT", record))
    return target, record


def settle_pending(*, journal, later_csv, now=None):
    base = Path(journal)
    settled, blocked, skipped = [], [], []
    for p in sorted((base / "observations").glob("*.json")):
        out = base / "settlements" / p.name
        if out.exists():
            skipped.append(p.name)
            continue
        try:
            dest, record = settle_one(p, later_csv, journal=journal, now=now)
            settled.append({"file": str(dest), "result": record["result"]})
        except (ValueError, OSError, KeyError, TypeError) as exc:
            blocked.append({"file": p.name, "reason": str(exc)})
    return {"settled": settled, "still_pending_or_blocked": blocked, "already_settled": skipped}


def prospective_scorecard(journal, payout=0.80):
    from scripts.stage55_statistical_audit import audit_holdout
    if not (0 < float(payout) <= 1):
        raise ValueError("Invalid payout")
    base = Path(journal)
    counts = {"WIN": 0, "LOSS": 0, "PUSH": 0, "ABSTAINED": 0}
    rejected = []
    for p in sorted((base / "settlements").glob("*.json")):
        try:
            record = _load_envelope(p, "SETTLEMENT")
            obspath = base / "observations" / p.name
            obs = _load_envelope(obspath, "OBSERVATION")
            if record["observation_sha256"] != digest(obs):
                raise ValueError("Settlement no longer matches observation")
            if record["result"] not in counts:
                raise ValueError("Unrecognized settlement")
            if record["research_hypothesis"] != obs["research_hypothesis"]:
                raise ValueError("Hypothesis mismatch")
            if record["expiry_time_utc"] != obs["expiry_time_utc"]:
                raise ValueError("Expiry mismatch")
            if utc(obs["recorded_at_utc"]) >= utc(obs["expiry_time_utc"]):
                raise ValueError("Observation created too late")
            if utc(record["recorded_at_utc"]) < utc(obs["expiry_time_utc"]):
                raise ValueError("Outcome recorded before expiry")
            counts[record["result"]] += 1
        except (OSError, ValueError, KeyError, TypeError) as exc:
            rejected.append({"file": str(p), "reason": str(exc)})
    # DO NOT certify direction if broker parity and provider attestation unverified.
    audit = audit_holdout({"wins": counts["WIN"], "losses": counts["LOSS"], "pushes": counts["PUSH"]}, payout=payout, minimum_resolved=100)
    return {
        "mode": "PROSPECTIVE_RESEARCH_HYPOTHESIS",
        "counts": counts, "invalid_evidence": rejected,
        "statistical_audit": audit,
        "prediction_accuracy_verified": False,
        "why_not_verified": "No broker-feed parity; provider evidence from local CSV not independently attested; observations may be dependent",
        "live_signal": "NO TRADE", "broker_orders": 0,
    }
