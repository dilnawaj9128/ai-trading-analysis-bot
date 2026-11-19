import pytest

from research.stage35_accuracy_audit import audit_accuracy, wilson_interval


def test_zero_observations_cannot_establish_accuracy():
    result = audit_accuracy(wins=0, losses=0)
    assert result["verdict"] == "INSUFFICIENT"
    assert result["win_rate"] is None
    assert result["wilson_95_lower"] is None


def test_known_stage31_holdout_is_insufficient():
    result = audit_accuracy(wins=7, losses=9, payout=0.8)
    assert result["resolved"] == 16
    assert result["win_rate"] == 0.4375
    assert result["hypothetical_net_units"] == -3.4
    assert result["verdict"] == "INSUFFICIENT"
    assert result["wilson_95_lower"] < result["break_even_win_rate"]


def test_perfect_tiny_sample_not_accepted():
    result = audit_accuracy(wins=10, losses=0)
    assert result["win_rate"] == 1
    assert result["verdict"] == "INSUFFICIENT"


def test_high_winrate_without_independent_validation_fails():
    result = audit_accuracy(wins=190, losses=10)
    assert result["verdict"] == "UNVERIFIED"


def test_high_winrate_without_provenance_fails():
    result = audit_accuracy(wins=190, losses=10, independent=True)
    assert result["verdict"] == "UNVERIFIED"


def test_verified_no_edge_stays_no_edge():
    result = audit_accuracy(wins=50, losses=50, independent=True,
                            provenance_verified=True)
    assert result["verdict"] == "NO EDGE"


def test_high_confidence_without_broker_parity_stays_research_only():
    result = audit_accuracy(wins=190, losses=10, independent=True,
                            provenance_verified=True)
    assert result["verdict"] == "RESEARCH ONLY"


def test_even_all_flags_do_not_claim_guaranteed_profit():
    result = audit_accuracy(wins=190, losses=10, independent=True,
                            provenance_verified=True, broker_parity_verified=True)
    assert result["verdict"] == "RESEARCH PASS"
    assert result["execution_enabled"] is False


def test_pushes_excluded_from_winrate_but_preserved():
    result = audit_accuracy(wins=7, losses=9, pushes=2)
    assert result["resolved"] == 16
    assert result["pushes"] == 2


def test_wilson_interval_valid_and_contained():
    low, high = wilson_interval(7, 9)
    assert 0 <= low < 0.4375 < high <= 1


def test_reject_bad_counts_and_payout():
    with pytest.raises(ValueError):
        audit_accuracy(wins=True, losses=2)
    with pytest.raises(ValueError):
        audit_accuracy(wins=-1, losses=2)
    with pytest.raises(ValueError):
        audit_accuracy(wins=2, losses=3, payout=float("nan"))
    with pytest.raises(ValueError):
        audit_accuracy(wins=2, losses=3, min_resolved=10)
