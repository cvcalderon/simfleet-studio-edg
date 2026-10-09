from __future__ import annotations

import math
import random

import pytest

from simfleet_edg.spatial.candidate_index import Candidate, CandidateIndex


def test_exact_oracle_random_and_adversarial() -> None:
    rng = random.Random(20261007)
    candidates = [Candidate(f"p{i:04d}", rng.uniform(-50000, 50000),
                            rng.uniform(-50000, 50000), rng.uniform(0.501, 1.499))
                  for i in range(275)]
    candidates.extend([Candidate("zero", 0, 0), Candidate("east", 1000, 0),
                       Candidate("west", -1000, 0)])
    index = CandidateIndex(candidates, leaf_size=7)
    for policy in ("S_NEAR", "S_DIST", "S_ATTR"):
        for x, y in ((0.0, 0.0), (750.0, -9000.0), (200000., 100000.)):
            for p in (1e-9, 0.001, 0.5, 1.0, 5., 10000., 1e9):
                actual = index.choose(x, y, p, policy)
                oracle = index.brute_force(x, y, p, policy)
                assert actual.location_id == oracle.location_id
                assert actual.distance_km == oracle.distance_km
                assert math.isclose(actual.compatibility, oracle.compatibility, abs_tol=0.0)


def test_near_tie_and_dist_undershoot_preference() -> None:
    index = CandidateIndex([Candidate("z", -1000, 0), Candidate("a", 1000, 0)])
    assert index.choose(0, 0, 1, "S_NEAR").location_id == "a"
    assert index.choose(0, 0, 1, "S_DIST").location_id == "a"
    assert index.choose(0, 0, 1, "S_ATTR").location_id == "a"


def test_reject_infinite_prior_coordinates_and_duplicate_ids() -> None:
    with pytest.raises(ValueError):
        CandidateIndex([])
    with pytest.raises(ValueError):
        CandidateIndex([Candidate("a", 0, 0), Candidate("a", 1, 1)])
    idx = CandidateIndex([Candidate("a", 0, 0)])
    for bad in (0, -1, math.nan, math.inf):
        with pytest.raises(ValueError):
            idx.choose(0, 0, bad, "S_DIST")
    with pytest.raises(ValueError):
        idx.choose(math.inf, 0, 1, "S_NEAR")
