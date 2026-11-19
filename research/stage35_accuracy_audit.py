"""Stage 35: conservative out-of-sample accuracy assessment, not optimization.

This module never changes trading thresholds or executes orders. It asks
whether a preselected strategy has enough independent verified observations
to establish a payout-adjusted edge; synthetic and unverified inputs may be
reported as research but cannot be certified.
"""
from __future__ import annotations

import math
from statistics import NormalDist


def wilson_interval(wins: int, losses: int, confidence: float = 0.95):
    """Two-sided Wilson score interval for resolved (non-push) observations."""
    if type(wins) is not int or type(losses) is not int or min(wins, losses) < 0:
        raise ValueError("Counts must be non-negative integers")
    if not isinstance(confidence, (float, int)) or not 0 < confidence < 1:
        raise ValueError("Invalid confidence level")
    n = wins + losses
    if not n:
        return None
    z = NormalDist().inv_cdf((1 + confidence) / 2)
    p = wins / n
    d = 1 + z * z / n
    center = (p + z * z / (2 * n)) / d
    margin = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (max(0.0, center - margin), min(1.0, center + margin))


def audit_accuracy(*, wins: int, losses: int, pushes: int = 0,
                   payout: float = 0.80, min_resolved: int = 100,
                   independent: bool = False, provenance_verified: bool = False,
                   broker_parity_verified: bool = False):
    """Strict reporting gate. 'PASS' is statistical evidence, not a guarantee.

    Requires an untouched independent sample and independently attested data.
    Even a PASS without broker price/payout parity cannot imply deployability.
    """
    if any(type(x) is not int or x < 0 for x in (wins, losses, pushes)):
        raise ValueError("Counts must be non-negative integers")
    if type(min_resolved) is not int or min_resolved < 100:
        raise ValueError("At least 100 resolved outcomes required")
    if type(payout) not in (float, int) or not math.isfinite(payout) or not 0 < payout <= 1:
        raise ValueError("Invalid payout")
    if any(type(x) is not bool for x in (independent, provenance_verified, broker_parity_verified)):
        raise ValueError("Verification flags must be booleans")
    resolved = wins + losses
    interval = wilson_interval(wins, losses)
    breakeven = 1 / (1 + payout)
    net = round(wins * payout - losses, 8)
    win_rate = wins / resolved if resolved else None
    if resolved < min_resolved:
        verdict, reason = "INSUFFICIENT", "Too few independent resolved observations"
    elif not independent:
        verdict, reason = "UNVERIFIED", "Holdout independence not established"
    elif not provenance_verified:
        verdict, reason = "UNVERIFIED", "Historical provider provenance not established"
    elif interval[0] <= breakeven:
        verdict, reason = "NO EDGE", "95% Wilson lower bound does not exceed payout break-even"
    elif not broker_parity_verified:
        verdict, reason = "RESEARCH ONLY", "Possible statistical edge; broker price/payout parity unverified"
    else:
        verdict, reason = "RESEARCH PASS", "Statistical evidence in this sample; no forward profit guarantee"
    return {"resolved": resolved, "pushes": pushes, "win_rate": win_rate,
            "wilson_95_lower": interval[0] if interval else None,
            "wilson_95_upper": interval[1] if interval else None,
            "payout": payout, "break_even_win_rate": breakeven,
            "hypothetical_net_units": net, "verdict": verdict, "reason": reason,
            "analysis_only": True, "execution_enabled": False}
