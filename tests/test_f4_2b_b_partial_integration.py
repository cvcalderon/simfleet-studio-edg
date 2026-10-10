"""Whole-day linkage and non-ESCORT S_DIST calls only."""
from __future__ import annotations

from dataclasses import dataclass

from simfleet_edg.canonical.mobility import LocationRef, ResidentialAnchor
from simfleet_edg.spatial.escort_partial_day_index import OriginalDay, OriginalTrip
from simfleet_edg.spatial.escort_partial_integration import (
    STATUS_RESOLVED,
    STATUS_SPATIAL_FAILURE,
    STATUS_UNLINKED,
    integrate_escort_day,
    metric_trip,
)
from simfleet_edg.spatial.escort_target_anchor_extension import AnchorAssignment


@dataclass
class FakeSpatializer:
    anchors: dict[str, ResidentialAnchor]
    locations: dict[str, LocationRef]
    indices: dict[str, object]
    _visited: int = 0

    def metric(self, ref: LocationRef) -> tuple[float, float]:
        return ref.lon, ref.lat

    def _resolve(self, origin: LocationRef, p: float, purpose: str,
                 policy: str) -> LocationRef:
        assert policy == "S_DIST" and purpose == "SHOPPING"
        self._visited += 1
        return self.locations["shop"]


def _case() -> tuple[OriginalDay, dict[str, dict[str, str]], dict[tuple[str, str], AnchorAssignment], FakeSpatializer]:
    home = LocationRef("home", "HOME", 1, 1)
    school = LocationRef("school", "POI", 3, 3)
    shop = LocationRef("shop", "POI", 4, 3)
    spatial = FakeSpatializer({"h1": ResidentialAnchor("h1", home, "X", "C")},
                              {"school": school, "shop": shop}, {"SHOPPING": object()})
    trips = (
        OriginalTrip("r", 1, "p", "h1", "HOME", "ESCORT", 400, 410, 10, 1.0),
        OriginalTrip("r", 2, "p", "h1", "ESCORT", "SHOPPING", 420, 430, 10, 1.0),
        OriginalTrip("r", 3, "p", "h1", "SHOPPING", "HOME", 440, 450, 10, 1.0),
    )
    days = OriginalDay("r", "p", "h1", trips, True, True)
    events = {"r:1": {"status": "RESOLVED_LOCATION_ONLY", "target_person_id": "target",
                      "target_purpose": "EDUCATION", "target_location_id": "school"}}
    anchors = {("target", "EDUCATION"): AnchorAssignment(
        "target", "EDUCATION", "school", 1.0, "SIDECAR")}
    return days, events, anchors, spatial


def test_full_chain_exact_and_escort_following_origin() -> None:
    day, events, anchors, spatial = _case()
    answer = integrate_escort_day(day, events, anchors, spatial)  # type: ignore[arg-type]
    assert answer.status == STATUS_RESOLVED
    assert len(answer.trips) == 3
    assert answer.trips[0].destination is answer.trips[1].origin
    assert answer.trips[1].destination is answer.trips[2].origin
    assert spatial._visited == 1


def test_unresolved_link_never_promotes_partial_day() -> None:
    day, events, anchors, spatial = _case()
    events["r:1"]["status"] = "UNRESOLVED_NO_ELIGIBLE_PARTNER"
    answer = integrate_escort_day(day, events, anchors, spatial)  # type: ignore[arg-type]
    assert answer.status == STATUS_UNLINKED and not answer.trips


def test_missing_target_location_yields_whole_day_spatial_failure() -> None:
    day, events, anchors, spatial = _case()
    spatial.locations.pop("school")
    answer = integrate_escort_day(day, events, anchors, spatial)  # type: ignore[arg-type]
    assert answer.status == STATUS_SPATIAL_FAILURE and not answer.trips


def test_zero_euclidean_distance_means_inf_without_epsilon() -> None:
    _, _, _, spatial = _case()
    loc = LocationRef("same", "HOME", 1, 1)
    distance, err = metric_trip(spatial, loc, loc, 1.0)  # type: ignore[arg-type]
    assert distance == 0.0 and err == float("inf")
