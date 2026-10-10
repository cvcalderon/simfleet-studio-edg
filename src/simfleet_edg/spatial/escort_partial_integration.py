"""Per-variant complete-day ESCORT binding; frozen F4.2a S_DIST only."""
from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass

from simfleet_edg.canonical.mobility import LocationRef
from simfleet_edg.spatial.escort_partial_day_index import OriginalDay, OriginalTrip
from simfleet_edg.spatial.escort_target_anchor_extension import AnchorAssignment
from simfleet_edg.spatial.spatialize_core import OCCURRENCE, Spatializer

STATUS_CORE = "CORE_FROZEN_SPATIALIZED"
STATUS_UNLINKED = "ESCORT_LINK_INCOMPLETE"
STATUS_RESOLVED = "ESCORT_SPATIALIZED_SYNTHETIC_LOCATION_ONLY"
STATUS_SPATIAL_FAILURE = "ESCORT_SPATIAL_UNRESOLVED"


class SpatialDayFailure(Exception):
    """Recoverable full-day spatial failure; never emit a partial day."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class ResolvedTrip:
    original: OriginalTrip
    origin: LocationRef
    destination: LocationRef
    event_id: str
    target_person_id: str
    target_anchor_origin: str
    euclidean_distance_km: float
    abs_log_ratio: float


@dataclass(frozen=True)
class ResolvedDay:
    status: str
    reasons: tuple[str, ...]
    links_complete: bool
    trips: tuple[ResolvedTrip, ...]


def metric_trip(spatializer: Spatializer, origin: LocationRef,
                destination: LocationRef, prior: float) -> tuple[float, float]:
    if not math.isfinite(prior) or prior <= 0:
        raise ValueError("BLOCKED_M2_PRIOR")
    ox, oy = spatializer.metric(origin)
    dx, dy = spatializer.metric(destination)
    distance = math.hypot(dx - ox, dy - oy) / 1000.0
    # Frozen choice: d=0 retains +INF, not an epsilon-corrected ratio.
    ratio = abs(math.log(distance / prior)) if distance > 0 else math.inf
    return distance, ratio


def integrate_escort_day(day: OriginalDay, events: Mapping[str, dict[str, str]],
                         anchors: Mapping[tuple[str, str], AnchorAssignment],
                         spatializer: Spatializer) -> ResolvedDay:
    """Two independent gates: all event links, then all activity destinations.

    Caller must validate original M2 chain and event identity globally first.
    Spatial failure returns no partial trip rows, even after some nodes resolve.
    """
    if not day.has_escort:
        raise ValueError("BLOCKED_NOT_ESCORT_DAY")
    expected = [f"{day.row_id}:{t.trip_index}" for t in day.trips
                if t.destination_activity == "ESCORT"]
    if set(events) != set(expected):
        raise ValueError("BLOCKED_DAY_EVENT_SET")
    unresolved = sorted({row["status"] for row in events.values()
                         if row["status"] != "RESOLVED_LOCATION_ONLY"})
    if unresolved:
        return ResolvedDay(STATUS_UNLINKED, tuple(unresolved), False, ())
    if not day.trips or day.trips[0].origin_activity != "HOME":
        raise ValueError("BLOCKED_INITIAL_HOME")
    home = spatializer.anchors.get(day.household_id)
    if home is None:
        raise ValueError("BLOCKED_M1_C_HOME_GATE")
    origin = home.location
    resolved: list[ResolvedTrip] = []
    spatializer._visited = 0
    try:
        for trip in day.trips:
            event_id = ""
            target = ""
            anchor_origin = ""
            activity = trip.destination_activity
            if activity == "HOME":
                dest = home.location
            elif activity == "ESCORT":
                event_id = f"{day.row_id}:{trip.trip_index}"
                event = events[event_id]
                target = event["target_person_id"]
                purpose = "WORK_COMMUTE" if event["target_purpose"] == "WORK" else "EDUCATION"
                assignment = anchors.get((target, purpose))
                if assignment is None or assignment.location_id != event["target_location_id"]:
                    raise SpatialDayFailure("SPATIAL_TARGET_ANCHOR_MISMATCH")
                anchor_origin = assignment.origin
                if assignment.location_id not in spatializer.locations:
                    raise SpatialDayFailure("SPATIAL_TARGET_LOCATION_ABSENT")
                dest = spatializer.locations[assignment.location_id]
            elif activity in ("WORK", "EDUCATION"):
                purpose = "WORK_COMMUTE" if activity == "WORK" else "EDUCATION"
                assignment = anchors.get((day.person_id, purpose))
                if assignment is None:
                    # Missing globally required key is an input failure, not an S_DIST fallback.
                    raise ValueError("BLOCKED_STABLE_ANCHOR_COVERAGE")
                if assignment.location_id not in spatializer.locations:
                    raise SpatialDayFailure("SPATIAL_STABLE_LOCATION_ABSENT")
                dest = spatializer.locations[assignment.location_id]
            elif activity in OCCURRENCE:
                try:
                    dest = spatializer._resolve(origin, trip.distance_prior_km, activity, "S_DIST")
                except (ValueError, LookupError, KeyError) as exc:
                    raise SpatialDayFailure("SPATIAL_S_DIST_NO_ELIGIBLE") from exc
            else:
                raise ValueError("BLOCKED_UNSUPPORTED_ACTIVITY")
            try:
                dist, err = metric_trip(spatializer, origin, dest, trip.distance_prior_km)
            except (OverflowError, ValueError) as exc:
                raise SpatialDayFailure("SPATIAL_METRIC_FAILURE") from exc
            resolved.append(ResolvedTrip(trip, origin, dest, event_id, target,
                                         anchor_origin, dist, err))
            origin = dest
    except SpatialDayFailure as exc:
        return ResolvedDay(STATUS_SPATIAL_FAILURE, (exc.code,), True, ())
    if len(resolved) != len(day.trips):
        raise ValueError("BLOCKED_DAY_PARTIAL_OUTPUT")
    for left, right in zip(resolved, resolved[1:]):
        if (left.destination.location_id != right.origin.location_id
                or left.destination != right.origin):
            raise ValueError("BLOCKED_DAY_CHAIN_LOCATION_IDENTITY")
    return ResolvedDay(STATUS_RESOLVED, (), True, tuple(resolved))
