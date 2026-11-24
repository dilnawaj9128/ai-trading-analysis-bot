"""Offline tests with synthetic COUNT inputs, not fabricated market data."""
import math
import pytest
from scripts.stage55_statistical_audit import (
    audit_holdout, binomial_upper_tail, wilson_interval,
)
from scripts.run_stage55_robust_validation import report_path


def test_break_even_80pct():
    a = audit_holdout({'wins': 60, 'losses': 40, 'pushes': 0, 'resolved': 100})
    assert a['break_even_nonpush_win_rate_at_payout'] == pytest.approx(5/9)
    assert a['idealized_net_units'] == pytest.approx(8)
    assert a['nonpush_outcomes'] == 100


def test_no_sample_never_certifies():
    a = audit_holdout({'wins': 0, 'losses': 0, 'pushes': 3, 'resolved': 3})
    assert a['observed_nonpush_win_rate'] is None
    assert a['statistical_screen_passed'] is False


def test_small_winning_sample_fails():
    a = audit_holdout({'wins': 17, 'losses': 0, 'pushes': 0})
    assert a['status'] == 'INSUFFICIENT_SAMPLE'


def test_lose_everything_not_significant():
    a = audit_holdout({'wins': 0, 'losses': 150, 'pushes': 0})
    assert a['statistical_screen_passed'] is False
    assert a['one_sided_exact_pvalue_vs_break_even'] == 1.0


def test_strong_sample_only_exploratory():
    a = audit_holdout({'wins': 95, 'losses': 5, 'pushes': 0})
    assert a['status'] == 'EXPLORATORY_EDGE_SCREEN_PASSED'
    assert a['statistical_screen_passed'] is True


def test_exact_tail_known_case():
    assert binomial_upper_tail(3, 1, 0.5) == pytest.approx(5/16)


def test_wilson_bounds():
    lower, upper = wilson_interval(60, 40)
    assert 0 < lower < 0.6 < upper < 1


def test_pushes_not_counted_as_nonpush():
    a = audit_holdout({'wins': 50, 'losses': 40, 'pushes': 10, 'resolved': 100})
    assert a['nonpush_outcomes'] == 90
    assert a['minimum_sample_reached'] is False


def test_inconsistent_count_fails():
    with pytest.raises(ValueError):
        audit_holdout({'wins': 3, 'losses': 4, 'pushes': 1, 'resolved': 6})


def test_negative_counts_fail():
    with pytest.raises(ValueError):
        audit_holdout({'wins': -1, 'losses': 2, 'pushes': 0})


def test_no_report_collision():
    a = report_path('/a/x.csv', '/reports', '1'*64)
    b = report_path('/b/x.csv', '/reports', '2'*64)
    assert a != b


def test_output_remains_research_only():
    a = audit_holdout({'wins': 95, 'losses': 5, 'pushes': 0})
    assert 'trading recommendation' in a['limitations'][-1]


def test_stage29_resolved_excludes_pushes():
    a = audit_holdout({'wins': 9, 'losses': 8, 'pushes': 2, 'resolved': 17, 'signals': 19})
    assert a['nonpush_outcomes'] == 17
    assert a['settled_outcomes_including_pushes'] == 19
    assert a['source_resolved_convention'] == 'nonpush_wins_plus_losses'
    assert a['status'] == 'INSUFFICIENT_SAMPLE'


def test_stage29_resolved_includes_pushes():
    a = audit_holdout({'wins': 9, 'losses': 8, 'pushes': 2, 'resolved': 19, 'signals': 19})
    assert a['source_resolved_convention'] == 'all_settled_including_pushes'
    assert a['nonpush_outcomes'] == 17


def test_stage29_inconsistent_signals_rejected():
    with pytest.raises(ValueError, match='Inconsistent signal count'):
        audit_holdout({'wins': 9, 'losses': 8, 'pushes': 2, 'resolved': 17, 'signals': 17})


def test_resolved_count_bool_rejected():
    with pytest.raises(ValueError, match='Invalid resolved'):
        audit_holdout({'wins': 1, 'losses': 0, 'pushes': 0, 'resolved': True})
