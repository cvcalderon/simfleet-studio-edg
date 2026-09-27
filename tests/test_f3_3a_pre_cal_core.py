from __future__ import annotations

import numpy as np
import pandas as pd

from simfleet_edg.evaluation.cal_bootstrap import (
    household_bootstrap_multipliers,
    percentile_interval,
)
from simfleet_edg.evaluation.cal_calibration import sigmoid_calibration_decision
from simfleet_edg.evaluation.cal_joint_gate import JointGateInput, joint_cal_gate
from simfleet_edg.evaluation.cal_metrics import (
    departure_hour,
    total_variation_distance,
    trip_count_category,
    wasserstein_1d,
    weighted_bernoulli_logloss,
    weighted_categorical_logloss,
    weighted_discrete_crps,
    weighted_distribution,
)
from simfleet_edg.evaluation.cal_protocol import (
    bootstrap_seed,
    part_b_household_fold,
    runtime_draw_seed,
)
from simfleet_edg.evaluation.cal_selection import (
    GridScore,
    choose_within_family,
    promotion_decision,
)


def test_runtime_seed_deterministic_and_namespaced():
    a = runtime_draw_seed(20260926, "CAL_EVAL_V1", 10, "PART", 0)
    b = runtime_draw_seed(20260926, "CAL_EVAL_V1", 10, "PART", 0)
    c = runtime_draw_seed(20260926, "CAL_EVAL_V1", 10, "COUNT", 0)
    assert a == b
    assert a != c
    assert 0 <= a < 2**64


def test_bootstrap_seed_pair_specific():
    assert bootstrap_seed(20260926, "DG_PARTICIPATION", "A", "B") != bootstrap_seed(
        20260926, "DG_PARTICIPATION", "A", "C"
    )


def test_household_fold_atomic_and_deterministic():
    assert part_b_household_fold(101) == part_b_household_fold("101")
    assert 0 <= part_b_household_fold(101) < 5


def test_weighted_bernoulli_logloss_perfect_is_small():
    value = weighted_bernoulli_logloss([0, 1], [0.01, 0.99], [1, 1])
    assert value < 0.02


def test_weighted_categorical_logloss():
    probs = np.array([[0.8, 0.2], [0.1, 0.9]])
    assert weighted_categorical_logloss([0, 1], probs, [1, 1]) < 0.2


def test_discrete_crps_perfect_zero():
    pmf = np.array([[1, 0, 0], [0, 1, 0]], dtype=float)
    assert weighted_discrete_crps([1, 2], pmf, [1, 1], 1) == 0.0


def test_distribution_and_tvd():
    a = weighted_distribution(["x", "y"], [1, 1])
    b = pd.Series({"x": 1.0})
    assert np.isclose(total_variation_distance(a, b), 0.5)


def test_departure_hour_frozen_definition():
    assert departure_hour([0, 59, 60, 1439]).tolist() == ["0", "0", "1", "23"]


def test_trip_count_category_frozen_definition():
    assert trip_count_category([0, 11, 12, 99]).tolist() == ["0", "11", "12_PLUS", "12_PLUS"]


def test_wasserstein_identity_zero():
    assert wasserstein_1d([1, 2], [1, 1], [1, 2], [1, 1]) == 0.0


def test_bootstrap_household_atomicity():
    ids = ["h1", "h1", "h2", "h3", "h3"]
    m = household_bootstrap_multipliers(ids, replicates=10, seed=123)
    assert m.shape == (10, 5)
    assert np.array_equal(m[:, 0], m[:, 1])
    assert np.array_equal(m[:, 3], m[:, 4])


def test_bootstrap_deterministic():
    ids = ["h1", "h2", "h3"]
    a = household_bootstrap_multipliers(ids, replicates=5, seed=9)
    b = household_bootstrap_multipliers(ids, replicates=5, seed=9)
    assert np.array_equal(a, b)


def test_percentile_interval():
    ci = percentile_interval(range(1000))
    assert ci.replicates == 1000
    assert ci.lower < ci.median < ci.upper


def _score(artifact, candidate, grid, role, metric, hard=True, guard=True):
    return GridScore(artifact, candidate, grid, role, metric, hard, guard)


def test_choose_within_family_lowest_metric():
    scores = [
        _score("a1", "A", "G1", "CORE_CANDIDATE_A", 1.2),
        _score("a2", "A", "G2", "CORE_CANDIDATE_A", 1.1),
    ]
    assert choose_within_family(scores).grid_id == "G2"


def test_choose_within_family_lexical_tie():
    scores = [
        _score("a2", "A", "G2", "CORE_CANDIDATE_A", 1.0),
        _score("a1", "A", "G1", "CORE_CANDIDATE_A", 1.0),
    ]
    assert choose_within_family(scores).grid_id == "G1"


def test_choose_within_family_filters_failures():
    scores = [
        _score("a1", "A", "G1", "CORE_CANDIDATE_A", 0.1, hard=False),
        _score("a2", "A", "G2", "CORE_CANDIDATE_A", 1.0),
    ]
    assert choose_within_family(scores).grid_id == "G2"


def test_promotion_requires_all_conditions():
    inc = _score("ref", "REF", "REFERENCE", "REFERENCE_BASELINE", 1.0)
    ch = _score("a", "A", "G1", "CORE_CANDIDATE_A", 0.8)
    d = promotion_decision(inc, ch, practical_margin=0.1, bootstrap_ci_lower=0.01, bootstrap_ci_upper=0.3)
    assert d.promoted


def test_promotion_rejects_ci_touching_zero():
    inc = _score("ref", "REF", "REFERENCE", "REFERENCE_BASELINE", 1.0)
    ch = _score("a", "A", "G1", "CORE_CANDIDATE_A", 0.8)
    d = promotion_decision(inc, ch, practical_margin=0.1, bootstrap_ci_lower=0.0, bootstrap_ci_upper=0.3)
    assert not d.promoted
    assert "BOOTSTRAP_CI_NOT_STRICTLY_ABOVE_ZERO" in d.reasons


def test_promotion_rejects_margin():
    inc = _score("ref", "REF", "REFERENCE", "REFERENCE_BASELINE", 1.0)
    ch = _score("a", "A", "G1", "CORE_CANDIDATE_A", 0.96)
    d = promotion_decision(inc, ch, practical_margin=0.05, bootstrap_ci_lower=0.01, bootstrap_ci_upper=0.1)
    assert not d.promoted


def test_sigmoid_calibration_rule_pass():
    d = sigmoid_calibration_decision(
        uncalibrated_logloss=0.5,
        calibrated_logloss=0.497,
        uncalibrated_share_error=0.01,
        calibrated_share_error=0.014,
    )
    assert d.retained


def test_sigmoid_calibration_rule_fail_share():
    d = sigmoid_calibration_decision(
        uncalibrated_logloss=0.5,
        calibrated_logloss=0.497,
        uncalibrated_share_error=0.01,
        calibrated_share_error=0.016,
    )
    assert not d.retained


def test_joint_gate_pass_does_not_close_g2():
    d = joint_cal_gate(JointGateInput(0, 0, 0, False, False, True, False))
    assert d.pass_gate and d.test_open_authorized
    assert d.formal_g2 == "NOT_EVALUATED"


def test_joint_gate_blocks_hard_violation():
    d = joint_cal_gate(JointGateInput(1, 0, 0, False, False, True, False))
    assert not d.pass_gate
    assert not d.test_open_authorized
