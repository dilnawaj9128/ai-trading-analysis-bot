"""Offline statistical guardrails for historical 15-minute binary-outcome research.

No price prediction, model fitting, network use, or broker operations.
A p-value is descriptive unless the tested strategy and hypotheses were
fixed before observing the holdout, and it does not correct for selection.
"""
from __future__ import annotations

import math
from statistics import NormalDist


def wilson_interval(wins: int, losses: int, confidence: float = 0.95):
    """Two-sided Wilson interval for non-push outcomes; None if no outcomes."""
    validate_counts(wins, losses, 0)
    if not 0 < confidence < 1:
        raise ValueError('Confidence must be in (0,1)')
    n = wins + losses
    if n == 0:
        return None
    z = NormalDist().inv_cdf((1 + confidence) / 2)
    p = wins / n
    d = 1 + z*z/n
    center = (p + z*z/(2*n)) / d
    half = z * math.sqrt(p*(1-p)/n + z*z/(4*n*n)) / d
    return [max(0.0, center-half), min(1.0, center+half)]


def validate_counts(wins, losses, pushes):
    for v in (wins, losses, pushes):
        if type(v) is not int or v < 0:
            raise ValueError('Wins, losses and pushes must be nonnegative integers')


def binomial_upper_tail(wins: int, losses: int, null_win_rate: float) -> float | None:
    """Exact P[Binomial(n, p0) >= wins] using log-sum-exp."""
    validate_counts(wins, losses, 0)
    if not 0 < null_win_rate < 1:
        raise ValueError('Invalid null win rate')
    n = wins + losses
    if n == 0:
        return None
    if wins == 0:
        return 1.0
    logs = [math.lgamma(n+1)-math.lgamma(k+1)-math.lgamma(n-k+1)
            + k*math.log(null_win_rate) + (n-k)*math.log1p(-null_win_rate)
            for k in range(wins, n+1)]
    m = max(logs)
    return min(1.0, math.exp(m) * math.fsum(math.exp(v-m) for v in logs))


def audit_holdout(holdout: dict, *, payout=0.8, minimum_resolved=100):
    """Risk-aware summary. Count tests alone NEVER certify live skill."""
    if type(payout) not in (int, float) or not math.isfinite(payout) or not 0 < payout <= 1:
        raise ValueError('Payout must be in (0,1]')
    if type(minimum_resolved) is not int or minimum_resolved < 30:
        raise ValueError('Minimum resolved must be >=30')
    w, l, p = (holdout[k] for k in ('wins','losses','pushes'))
    validate_counts(w, l, p)
    n = w + l
    # Stage 29 variants use 'resolved' for either decided (non-push)
    # outcomes or all settled outcomes. Never silently count pushes as wins.
    resolved = holdout.get('resolved')
    if resolved is not None:
        if type(resolved) is not int or resolved < 0:
            raise ValueError('Invalid resolved holdout count')
        if resolved == n and resolved == n + p:
            resolved_convention = 'both_equivalent_no_pushes'
        elif resolved == n:
            resolved_convention = 'nonpush_wins_plus_losses'
        elif resolved == n + p:
            resolved_convention = 'all_settled_including_pushes'
        else:
            raise ValueError('Inconsistent resolved holdout count')
    else:
        resolved_convention = 'not_reported'
    # Optional signals count must not undercount actual recorded outcomes.
    signals = holdout.get('signals')
    if signals is not None:
        if type(signals) is not int or signals < n + p:
            raise ValueError('Inconsistent signal count')
    net = round(w*float(payout) - l, 10)
    break_even = 1 / (1 + float(payout))
    interval = wilson_interval(w, l)
    pval = binomial_upper_tail(w, l, break_even)
    # Use lower-bound plus exact test as *necessary*, not sufficient evidence.
    evidence_sufficient = n >= minimum_resolved and interval is not None and interval[0] > break_even and pval < 0.05
    return {
        'wins': w, 'losses': l, 'pushes': p,
        'nonpush_outcomes': n, 'settled_outcomes_including_pushes': n+p, 'resolved_outcomes': n+p,
        'source_resolved_count': resolved, 'source_resolved_convention': resolved_convention,
        'observed_nonpush_win_rate': (w/n if n else None),
        'break_even_nonpush_win_rate_at_payout': break_even,
        'wilson_95pct_nonpush_win_rate': interval,
        'one_sided_exact_pvalue_vs_break_even': pval,
        'idealized_net_units': net,
        'minimum_nonpush_outcomes': minimum_resolved,
        'minimum_sample_reached': n >= minimum_resolved,
        'statistical_screen_passed': bool(evidence_sufficient),
        'status': ('NO_OUTCOMES' if n == 0 else
                   'INSUFFICIENT_SAMPLE' if n < minimum_resolved else
                   'NO_STATISTICAL_EDGE_DEMONSTRATED' if not evidence_sufficient else
                   'EXPLORATORY_EDGE_SCREEN_PASSED'),
        'limitations': [
            'The tested strategy may have been selected after seeing these data (multiple-testing risk).',
            'Nonoverlapping trades reduce overlap but do not guarantee independent outcomes.',
            'Broker feed parity, execution slippage, payout variability and live performance are unverified.',
            'Statistical screening is not a calibrated prediction or a trading recommendation.',
        ],
    }
