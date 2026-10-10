"""Deterministic full-M2 ledgers with append-only ESCORT deltas.

CORE is represented by immutable source RunBundle+SHA, never reserialized.
"""
from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from typing import Any

from simfleet_edg.spatial.escort_partial_day_index import OriginalDay
from simfleet_edg.spatial.escort_partial_integration import (
    STATUS_CORE,
    STATUS_RESOLVED,
    ResolvedDay,
)

DAY_COLUMNS = ("variant_id", "row_id", "person_id", "household_id", "trip_count",
               "escort_event_count", "day_status", "reason_codes",
               "all_escort_links_resolved", "every_trip_spatialized")
TRIP_COLUMNS = ("variant_id", "row_id", "trip_index", "original_origin_activity",
                "original_destination_activity", "original_departure_clock_minute",
                "original_arrival_absolute_minute", "original_distance_prior_km",
                "spatial_status", "origin_location_id", "destination_location_id",
                "source_core_or_delta")
DELTA_COLUMNS = ("variant_id", "row_id", "person_id", "trip_index", "origin_activity",
                 "destination_activity", "origin_location_id", "destination_location_id",
                 "distance_prior_km", "event_id", "target_person_id", "target_anchor_origin",
                 "euclidean_distance_km", "abs_log_ratio")


def day_rows(days: Iterable[OriginalDay], resolutions: Mapping[str, ResolvedDay],
             variant: str) -> Iterable[dict[str, Any]]:
    for day in days:
        result = resolutions.get(day.row_id)
        if day.has_escort and result is None:
            raise ValueError("BLOCKED_ESCORT_DAY_NOT_ACCOUNTED")
        status = result.status if result is not None else STATUS_CORE
        count = sum(t.destination_activity == "ESCORT" for t in day.trips)
        yield {"variant_id": variant, "row_id": day.row_id, "person_id": day.person_id,
               "household_id": day.household_id, "trip_count": len(day.trips),
               "escort_event_count": count, "day_status": status,
               "reason_codes": json.dumps(result.reasons if result else [], separators=(",", ":")),
               "all_escort_links_resolved": bool(result.links_complete) if result else False,
               "every_trip_spatialized": status in (STATUS_CORE, STATUS_RESOLVED)}


def trip_rows(days: Iterable[OriginalDay], resolutions: Mapping[str, ResolvedDay],
              variant: str, core_locations: Mapping[tuple[str, int], tuple[str, str]]
              ) -> Iterable[dict[str, Any]]:
    for day in days:
        outcome = resolutions.get(day.row_id)
        accepted = outcome is not None and outcome.status == STATUS_RESOLVED
        if accepted and outcome is not None and len(outcome.trips) != len(day.trips):
            raise ValueError("BLOCKED_DELTA_PARTIAL_DAY")
        for i, trip in enumerate(day.trips):
            rt = outcome.trips[i] if accepted and outcome is not None else None
            core = core_locations.get((day.row_id, trip.trip_index)) if not day.has_escort else None
            if not day.has_escort and core is None:
                raise ValueError("BLOCKED_CORE_REFERENCE_MISSING_TRIP")
            yield {"variant_id": variant, "row_id": day.row_id,
                   "trip_index": trip.trip_index, "original_origin_activity": trip.origin_activity,
                   "original_destination_activity": trip.destination_activity,
                   "original_departure_clock_minute": trip.departure_clock_minute,
                   "original_arrival_absolute_minute": trip.arrival_absolute_minute,
                   "original_distance_prior_km": trip.distance_prior_km,
                   "spatial_status": "CORE_BY_REFERENCE" if not day.has_escort else (
                       "ESCORT_SPATIALIZED" if accepted else "ESCORT_UNSPATIALIZED"),
                   "origin_location_id": rt.origin.location_id if rt else (core[0] if core else ""),
                   "destination_location_id": rt.destination.location_id if rt else (core[1] if core else ""),
                   "source_core_or_delta": "F4_2A_CORE_REFERENCE" if not day.has_escort else (
                       "F4_2B_B_DELTA" if accepted else "NONE")}


def delta_rows(days: Iterable[OriginalDay], resolutions: Mapping[str, ResolvedDay],
               variant: str) -> Iterable[dict[str, Any]]:
    for day in days:
        if not day.has_escort:
            continue
        outcome = resolutions[day.row_id]
        if outcome.status != STATUS_RESOLVED:
            continue
        if len(outcome.trips) != len(day.trips):
            raise ValueError("BLOCKED_DELTA_PARTIAL_DAY")
        for rt in outcome.trips:
            t = rt.original
            yield {"variant_id": variant, "row_id": day.row_id,
                   "person_id": day.person_id, "trip_index": t.trip_index,
                   "origin_activity": t.origin_activity,
                   "destination_activity": t.destination_activity,
                   "origin_location_id": rt.origin.location_id,
                   "destination_location_id": rt.destination.location_id,
                   "distance_prior_km": t.distance_prior_km,
                   "event_id": rt.event_id, "target_person_id": rt.target_person_id,
                   "target_anchor_origin": rt.target_anchor_origin,
                   "euclidean_distance_km": rt.euclidean_distance_km,
                   "abs_log_ratio": "INF" if rt.abs_log_ratio == float("inf") else rt.abs_log_ratio}
