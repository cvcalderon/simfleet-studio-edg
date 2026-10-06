from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from math import isfinite


def _nonempty(value: str, field: str) -> str:
    text = str(value)
    if not text:
        raise ValueError(f"{field} must be non-empty")
    return text


@dataclass(frozen=True, slots=True)
class ActivityIntent:
    activity_index: int
    activity: str
    arrival_absolute_minute: int | None
    departure_clock_minute: int | None

    def __post_init__(self) -> None:
        if self.activity_index < 0:
            raise ValueError("activity_index must be >= 0")
        _nonempty(self.activity, "activity")
        if self.arrival_absolute_minute is not None and self.arrival_absolute_minute < 0:
            raise ValueError("arrival_absolute_minute must be >= 0")
        if self.departure_clock_minute is not None and not 0 <= self.departure_clock_minute < 1440:
            raise ValueError("departure_clock_minute must be in [0, 1440)")


@dataclass(frozen=True, slots=True)
class TripDemand:
    trip_index: int
    origin_activity: str
    destination_activity: str
    departure_clock_minute: int
    arrival_absolute_minute: int
    duration_from_clock_min: int
    distance_prior_km: float

    def __post_init__(self) -> None:
        if self.trip_index < 1:
            raise ValueError("trip_index must be >= 1")
        _nonempty(self.origin_activity, "origin_activity")
        _nonempty(self.destination_activity, "destination_activity")
        if not 0 <= self.departure_clock_minute < 1440:
            raise ValueError("departure_clock_minute must be in [0, 1440)")
        if self.arrival_absolute_minute < 0:
            raise ValueError("arrival_absolute_minute must be >= 0")
        if self.duration_from_clock_min <= 0:
            raise ValueError("duration_from_clock_min must be > 0")
        if not isfinite(self.distance_prior_km) or self.distance_prior_km <= 0:
            raise ValueError("distance_prior_km must be positive and finite")


@dataclass(frozen=True, slots=True)
class PersonDayPlan:
    person_id: str
    household_id: str
    day_id: str
    pipeline: str
    replicate_index: int
    trip_day: bool
    trips: tuple[TripDemand, ...]
    activities: tuple[ActivityIntent, ...]
    return_home: bool
    temporal_chain_valid: bool
    distance_chain_valid: bool

    def __post_init__(self) -> None:
        _nonempty(self.person_id, "person_id")
        _nonempty(self.household_id, "household_id")
        _nonempty(self.day_id, "day_id")
        _nonempty(self.pipeline, "pipeline")
        if self.replicate_index < 0:
            raise ValueError("replicate_index must be >= 0")
        if len(self.trips) != (len(self.activities) - 1 if self.activities else 0):
            raise ValueError("activity/trip chain cardinality mismatch")
        if self.trip_day != bool(self.trips):
            raise ValueError("trip_day must equal bool(trips)")


@dataclass(frozen=True, slots=True)
class LocationRef:
    location_id: str
    level: str
    lon: float
    lat: float
    crs: str = "EPSG:4326"

    def __post_init__(self) -> None:
        _nonempty(self.location_id, "location_id")
        _nonempty(self.level, "level")
        _nonempty(self.crs, "crs")
        if not isfinite(self.lon) or not isfinite(self.lat):
            raise ValueError("location coordinates must be finite")


@dataclass(frozen=True, slots=True)
class ResidentialAnchor:
    household_id: str
    location: LocationRef
    parent_bezirk_id: str
    provenance: str

    def __post_init__(self) -> None:
        _nonempty(self.household_id, "household_id")
        _nonempty(self.parent_bezirk_id, "parent_bezirk_id")
        _nonempty(self.provenance, "provenance")


@dataclass(frozen=True, slots=True)
class LocationSupplyRecord:
    location: LocationRef
    eligible_purposes: tuple[str, ...]
    attractiveness: float | None
    capacity: float | None
    provenance: str

    def __post_init__(self) -> None:
        if not self.eligible_purposes:
            raise ValueError("eligible_purposes must be non-empty")
        if self.attractiveness is not None:
            if not isfinite(self.attractiveness) or self.attractiveness < 0:
                raise ValueError("attractiveness must be finite and >= 0")
        if self.capacity is not None:
            if not isfinite(self.capacity) or self.capacity < 0:
                raise ValueError("capacity must be finite and >= 0")
        _nonempty(self.provenance, "provenance")


@dataclass(frozen=True, slots=True)
class SpatialTripIntent:
    demand: TripDemand
    origin: LocationRef
    destination: LocationRef


@dataclass(frozen=True, slots=True)
class SpatializedDayPlan:
    base_plan: PersonDayPlan
    home_anchor: ResidentialAnchor
    trips: tuple[SpatialTripIntent, ...]


@dataclass(frozen=True, slots=True)
class PopulationSnapshotAdapter:
    person_to_household: Mapping[str, str]
    household_home_context: Mapping[str, tuple[str, str]]

    def household_for(self, person_id: str) -> str:
        try:
            return self.person_to_household[person_id]
        except KeyError as exc:
            raise KeyError(f"Unknown person_id: {person_id}") from exc

    def home_context_for_household(self, household_id: str) -> tuple[str, str]:
        try:
            return self.household_home_context[household_id]
        except KeyError as exc:
            raise KeyError(f"Unknown household_id: {household_id}") from exc
