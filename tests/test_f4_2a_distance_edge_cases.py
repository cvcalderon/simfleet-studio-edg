import math

import pytest

from simfleet_edg.spatial.candidate_index import Candidate, CandidateIndex
from simfleet_edg.spatial.candidate_policies import abs_log_ratio, compatibility


def test_exact_zero_prefers_positive_target_if_available() -> None:
    idx = CandidateIndex([Candidate("zero", 0, 0), Candidate("one", 1000, 0)])
    assert idx.choose(0, 0, 1., "S_DIST").location_id == "one"
    zero = idx.brute_force(0, 0, 0.0001, "S_NEAR")
    assert zero.location_id == "zero"
    assert abs_log_ratio(zero.distance_km, 0.0001) == math.inf
    assert compatibility(zero.distance_km, 0.0001) == 0


def test_abs_log_ratio_requires_strict_positive_prior() -> None:
    with pytest.raises(ValueError):
        abs_log_ratio(1, 0)
    with pytest.raises(ValueError):
        abs_log_ratio(math.inf, 1)
    assert abs_log_ratio(1, 1) == 0
