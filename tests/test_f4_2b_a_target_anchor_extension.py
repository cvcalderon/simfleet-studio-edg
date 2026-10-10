from __future__ import annotations

import pytest

from simfleet_edg.canonical.mobility import LocationRef, ResidentialAnchor
from simfleet_edg.spatial.candidate_index import Candidate, CandidateIndex
from simfleet_edg.spatial.escort_event_index import M2Index
from simfleet_edg.spatial.escort_target_anchor_extension import (
    AnchorAssignment,
    extend_stable_anchors,
)
from simfleet_edg.spatial.spatial_core_io import FrozenSupply


def test_missing_anchor_sidecar_and_overlap_guard() -> None:
    home = LocationRef("home", "POINT", 13.4, 52.5)
    loc = LocationRef("edu", "POINT", 13.405, 52.505)
    homeanchor = ResidentialAnchor("hh", home, "bez", "SOURCE")
    supply = FrozenSupply((), {"hh": homeanchor},
        {"EDUCATION": CandidateIndex([Candidate("edu", 392000, 5818000)])},
        {"edu": loc}, {})
    index = M2Index((), {"p": "hh"}, {"p": frozenset({"EDUCATION"})},
                    {("p", "EDUCATION"): 1.5}, 1, 1, 0, 0)
    all_, missing = extend_stable_anchors(index, supply, {})
    assert len(missing) == 1
    assert all_[("p", "EDUCATION")].location_id == "edu"
    same = {("p", "EDUCATION"): missing[0]}
    again, empty = extend_stable_anchors(index, supply, same)
    assert not empty and again[("p", "EDUCATION")].location_id == "edu"
    bad = {("p", "EDUCATION"): AnchorAssignment("p", "EDUCATION", "wrong", 1.5, "CORE")}
    with pytest.raises(ValueError, match="CORE overlap mismatch"):
        extend_stable_anchors(index, supply, bad)
