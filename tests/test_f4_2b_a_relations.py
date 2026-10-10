from __future__ import annotations

from simfleet_edg.spatial.escort_event_index import EscortEvent, M2Index
from simfleet_edg.spatial.escort_synthetic_relations import (
    PartnerPools,
    Variant,
    draw_purpose,
    keyed_uniform,
    propose,
)
from simfleet_edg.spatial.escort_target_anchor_extension import AnchorAssignment


def fixtures() -> tuple[PartnerPools, dict[tuple[str, str], AnchorAssignment]]:
    index = M2Index((), {"self": "a", "one": "a", "two": "b", "three": "c"},
                    {"one": frozenset({"EDUCATION"}), "two": frozenset({"EDUCATION"}),
                     "three": frozenset({"EDUCATION"})}, {}, 4, 4, 0, 0)
    anchors = {("one", "EDUCATION"): AnchorAssignment("one", "EDUCATION", "x", 1, "SIDECAR"),
               ("two", "EDUCATION"): AnchorAssignment("two", "EDUCATION", "y", 1, "SIDECAR"),
               ("three", "EDUCATION"): AnchorAssignment("three", "EDUCATION", "z", 1, "SIDECAR")}
    return PartnerPools(index, anchors), anchors


def test_keyed_hash_uniform_stable_and_b0() -> None:
    pools, anchors = fixtures()
    x = keyed_uniform("s", "d", "r:1", "v", "sha", "EDUCATION", "SCOPE")
    assert x == keyed_uniform("s", "d", "r:1", "v", "sha", "EDUCATION", "SCOPE")
    assert 0 <= x < 1
    assert x != keyed_uniform("s", "d", "r:1", "v", "sha", "EDUCATION", "PARTNER")
    ev = EscortEvent("r", 1, "self", "a", 100, 90)
    record = propose(ev, None, pools, anchors, scenario="s", day="d", prior_sha="sha")
    assert record["status"] == "UNRESOLVED_B0_NO_LINK"
    assert not record["target_person_id"]


def test_no_cross_scope_and_complement_uniform() -> None:
    pools, _ = fixtures()
    assert pools.pick("EDUCATION", "self", "a", True, 0.3) == ("one", "RESOLVED_LOCATION_ONLY")
    assert pools.pick("EDUCATION", "self", "a", False, 0.0) == ("three", "RESOLVED_LOCATION_ONLY")
    assert pools.pick("EDUCATION", "self", "a", False, 0.99) == ("two", "RESOLVED_LOCATION_ONLY")
    assert pools.pick("EDUCATION", "two", "b", True, 0.5)[1] == "UNRESOLVED_NO_ELIGIBLE_PARTNER"


def test_unsupported_mass_never_renormalized() -> None:
    v = Variant("v", "2018", 0.25, .739, .025, .236)
    assert draw_purpose(.738, v) == "EDUCATION"
    assert draw_purpose(.750, v) == "WORK"
    assert draw_purpose(.764, v) == "UNSUPPORTED_PURPOSE"
    assert draw_purpose(.999, v) == "UNSUPPORTED_PURPOSE"


def test_anchor_missing_typed_and_no_fallback() -> None:
    index = M2Index((), {"self": "a", "other": "z"},
        {"other": frozenset({"WORK"})}, {}, 2, 1, 0, 0)
    other = PartnerPools(index, {})
    assert other.pick("WORK", "self", "a", False, .5) == (None, "UNRESOLVED_TARGET_ANCHOR")
    assert other.pick("WORK", "self", "a", True, .5) == (None, "UNRESOLVED_NO_ELIGIBLE_PARTNER")
