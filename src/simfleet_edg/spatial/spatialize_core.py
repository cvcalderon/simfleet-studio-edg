"""F4.2a trip->activity-node spatialization against frozen M2 and M3-C.

No mode, route, realized service or future outcome is consumed here.
"""
from __future__ import annotations

import math
import statistics
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Final

from pyproj import Transformer

from simfleet_edg.canonical.mobility import (
    LocationRef,
    PersonDayPlan,
    ResidentialAnchor,
    SpatializedDayPlan,
    SpatialTripIntent,
)
from simfleet_edg.spatial.candidate_index import CandidateIndex
from simfleet_edg.spatial.candidate_policies import Policy, abs_log_ratio

METRIC: Final[str] = "EPSG:25833"
SOURCE: Final[str] = "EPSG:4326"
STABLE: Final[dict[str, str]] = {"WORK": "WORK_COMMUTE", "EDUCATION": "EDUCATION"}
OCCURRENCE: Final[frozenset[str]] = frozenset({"BUSINESS", "SHOPPING", "LEISURE", "OTHER"})


@dataclass(frozen=True, slots=True)
class StableAssignment:
    person_id: str
    purpose: str
    location_id: str
    prior_aggregate_km: float


@dataclass(frozen=True, slots=True)
class CoreSpatialized:
    days: tuple[SpatializedDayPlan, ...]
    exclusions: tuple[PersonDayPlan, ...]
    stable_locations: tuple[StableAssignment, ...]
    index_candidate_visits: int


class Spatializer:
    """Reuses only C-supplied destinations and household-specific frozen anchors."""

    def __init__(self, indices: Mapping[str, CandidateIndex],
                 locations: Mapping[str, LocationRef],
                 anchors: Mapping[str, ResidentialAnchor]) -> None:
        self.indices = dict(indices)
        self.locations = dict(locations)
        self.anchors = dict(anchors)
        self._to_m = Transformer.from_crs(SOURCE, METRIC, always_xy=True)
        self._projected: dict[str, tuple[float, float]] = {}
        self._visited = 0

    def metric(self, ref: LocationRef) -> tuple[float, float]:
        if ref.location_id not in self._projected:
            if ref.crs != SOURCE:
                raise ValueError("C locations must have frozen EPSG:4326 coordinates")
            x, y = self._to_m.transform(ref.lon, ref.lat)
            if not math.isfinite(x) or not math.isfinite(y):
                raise ValueError("Invalid C projected coordinates")
            self._projected[ref.location_id] = (float(x), float(y))
        return self._projected[ref.location_id]

    def _resolve(self, origin: LocationRef, p: float, purpose: str,
                 policy: Policy) -> LocationRef:
        if purpose not in self.indices:
            raise ValueError(f"No frozen C eligible supply for {purpose}")
        x, y = self.metric(origin)
        index = self.indices[purpose]
        choice = index.choose(x, y, p, policy)
        self._visited += index.last_visited
        return self.locations[choice.location_id]

    def spatialize(self, plans: tuple[PersonDayPlan, ...], policy: Policy) -> CoreSpatialized:
        if len({(p.person_id, p.day_id, p.replicate_index) for p in plans}) != len(plans):
            raise ValueError("Duplicate day-plan identities")
        self._visited = 0
        days: list[SpatializedDayPlan] = []
        exclusions: list[PersonDayPlan] = []
        assignments: list[StableAssignment] = []
        stable_by_person: dict[tuple[str, str], str] = {}
        for plan in plans:
            anchor = self.anchors.get(plan.household_id)
            if anchor is None:
                raise ValueError(f"M1 household lacks frozen C anchor: {plan.household_id}")
            if any("ESCORT" in (t.origin_activity, t.destination_activity) for t in plan.trips):
                exclusions.append(plan)
                continue
            if not plan.trips:
                if plan.trip_day or plan.activities:
                    raise ValueError("NoTrip requires empty activities and no fake trips")
                days.append(SpatializedDayPlan(plan, anchor, ()))
                continue
            if plan.trips[0].origin_activity != "HOME":
                raise ValueError(f"MAIN_BLOCKER_INITIAL_NON_HOME: {plan.person_id}")
            for left, right in zip(plan.trips, plan.trips[1:]):
                if left.destination_activity != right.origin_activity:
                    raise ValueError("Frozen M2 activity chain is discontinuous")
            # Compute person-stable locations from the HOME point, never from a
            # realized prior-day trajectory. If a second day exists, re-use id.
            stable: dict[str, LocationRef] = {}
            for activity, purpose in STABLE.items():
                incoming = [t for t in plan.trips if t.destination_activity == activity]
                if not incoming:
                    continue
                home_origin = [t.distance_prior_km for t in incoming if t.origin_activity == "HOME"]
                priors = home_origin if home_origin else [t.distance_prior_km for t in incoming]
                target = float(statistics.median(priors))
                key = (plan.person_id, purpose)
                if key in stable_by_person:
                    location = self.locations[stable_by_person[key]]
                else:
                    location = self._resolve(anchor.location, target, purpose, policy)
                    stable_by_person[key] = location.location_id
                    assignments.append(StableAssignment(plan.person_id, purpose, location.location_id, target))
                stable[activity] = location
            origin = anchor.location
            resolved: list[SpatialTripIntent] = []
            for trip in plan.trips:
                if trip.destination_activity == "HOME":
                    dest = anchor.location
                elif trip.destination_activity in stable:
                    dest = stable[trip.destination_activity]
                elif trip.destination_activity in OCCURRENCE:
                    dest = self._resolve(origin, trip.distance_prior_km, trip.destination_activity, policy)
                else:
                    raise ValueError(f"Unsupported frozen M3 activity: {trip.destination_activity}")
                ox, oy = self.metric(origin)
                dx, dy = self.metric(dest)
                distance = math.hypot(dx - ox, dy - oy) / 1000.0
                abs_log_ratio(distance, trip.distance_prior_km)
                resolved.append(SpatialTripIntent(trip, origin, dest))
                origin = dest
            days.append(SpatializedDayPlan(plan, anchor, tuple(resolved)))
        return CoreSpatialized(tuple(days), tuple(exclusions), tuple(assignments), self._visited)
