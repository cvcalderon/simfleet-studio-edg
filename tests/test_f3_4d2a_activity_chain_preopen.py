from __future__ import annotations

import math

import pytest

from simfleet_edg.evaluation.activity_chain_cal_preopen import (
    ACTIVITIES,
    absolute_return_home_error,
    categorical_draw,
    derive_uint64,
    paired_household_bootstrap,
    tvd,
    uniform01,
    validate_chain,
    weighted_log_loss,
    weighted_shares,
)


def test_seed_derivation_is_deterministic():
    a = derive_uint64(20260926, "S", "P1", "DG_ACTIVITY_CHAIN", 3)
    b = derive_uint64(20260926, "S", "P1", "DG_ACTIVITY_CHAIN", 3)
    assert a == b


def test_crn_namespace_excludes_candidate_identity():
    seed = derive_uint64(20260926, "S", "P1", "DG_ACTIVITY_CHAIN", 3)
    assert 0.0 <= uniform01(seed) < 1.0


def test_weighted_log_loss_matches_manual_value():
    targets = ["HOME", "WORK"]
    pmfs = [
        {"HOME": 0.8, "WORK": 0.2},
        {"HOME": 0.25, "WORK": 0.75},
    ]
    actual = weighted_log_loss(targets, pmfs, [1.0, 1.0])
    expected = (-math.log(0.8) - math.log(0.75)) / 2
    assert actual == pytest.approx(expected)


def test_weighted_shares_and_tvd():
    observed = weighted_shares(["HOME", "WORK"], [1.0, 1.0], ACTIVITIES)
    generated = weighted_shares(["HOME", "HOME"], [1.0, 1.0], ACTIVITIES)
    assert tvd(observed, generated, ACTIVITIES) == pytest.approx(0.5)


def test_return_home_share_absolute_error():
    err = absolute_return_home_error(
        ["HOME", "HOME"],
        ["HOME", "WORK"],
        [1.0, 1.0],
    )
    assert err == pytest.approx(0.5)


def test_categorical_draw_is_valid():
    draw = categorical_draw(
        {"HOME": 0.5, "WORK": 0.5},
        0.75,
    )
    assert draw == "WORK"


def test_chain_invariant():
    validate_chain(["HOME", "WORK", "HOME"], 2)
    with pytest.raises(ValueError):
        validate_chain(["HOME", "WORK"], 2)


def test_paired_household_bootstrap_is_reproducible():
    diffs = {"H1": 0.1, "H2": 0.2, "H3": 0.3}
    a = paired_household_bootstrap(diffs, replicates=100, master_seed=17)
    b = paired_household_bootstrap(diffs, replicates=100, master_seed=17)
    assert a == b
    assert a[0] <= a[1] <= a[2]
