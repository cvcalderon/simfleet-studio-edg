"""Immutable F4.2a person-day and trip identities for F4.2b-B.

This module reads only generated M2 CSVs, never executes the demand generator.
"""
from __future__ import annotations

import csv
import gzip
import math
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

import pandas as pd  # type: ignore[import-untyped]

ACTIVITIES = frozenset({"HOME", "WORK", "EDUCATION", "BUSINESS", "SHOPPING",
                        "LEISURE", "OTHER", "ESCORT"})


@dataclass(frozen=True)
class OriginalTrip:
    row_id: str
    trip_index: int
    person_id: str
    household_id: str
    origin_activity: str
    destination_activity: str
    departure_clock_minute: int
    arrival_absolute_minute: int
    duration_from_clock_min: int
    distance_prior_km: float


@dataclass(frozen=True)
class OriginalDay:
    row_id: str
    person_id: str
    household_id: str
    trips: tuple[OriginalTrip, ...]
    has_escort: bool
    return_home: bool


def _read(path: Path) -> list[dict[str, str]]:
    with gzip.open(path, "rt", encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def _flag(raw: str) -> bool:
    if str(raw).strip().lower() in {"1", "true"}:
        return True
    if str(raw).strip().lower() in {"0", "false"}:
        return False
    raise ValueError("BLOCKED_M2_BOOLEAN: " + str(raw))


def load_original_days(root: Path, *, strict: bool = True) -> tuple[OriginalDay, ...]:
    """Preserve CSV identity/order and frozen pandas distance-prior conversions."""
    day_rows = _read(root / "dgen_A/dgen_day_rows_v1.csv.gz")
    trip_path = root / "dgen_A/dgen_trip_rows_v1.csv.gz"
    trip_rows = _read(trip_path)
    numeric = pd.read_csv(trip_path, low_memory=False)["distance_prior_km"].to_numpy()
    if len(numeric) != len(trip_rows):
        raise ValueError("BLOCKED_M2_PANDAS_ALIGNMENT")
    if len({row["row_id"] for row in day_rows}) != len(day_rows):
        raise ValueError("BLOCKED_M2_DUPLICATE_DAY")
    grouped: dict[str, list[OriginalTrip]] = defaultdict(list)
    used: set[tuple[str, int]] = set()
    for raw, prior in zip(trip_rows, numeric, strict=True):
        rid = raw["row_id"]
        ix = int(raw["trip_index"])
        key = (rid, ix)
        if key in used:
            raise ValueError("BLOCKED_M2_DUPLICATE_TRIP")
        used.add(key)
        p = float(prior)
        if not math.isfinite(p) or p <= 0:
            raise ValueError("BLOCKED_M2_DISTANCE_PRIOR")
        trip = OriginalTrip(rid, ix, raw["source_person_id"],
                            raw["source_household_id"], raw["origin_activity"],
                            raw["destination_activity"], int(raw["departure_clock_minute"]),
                            int(raw["arrival_absolute_minute"]),
                            int(raw["duration_from_clock_min"]), p)
        if ({trip.origin_activity, trip.destination_activity} - ACTIVITIES or ix < 1
                or not 0 <= trip.departure_clock_minute < 1440
                or trip.arrival_absolute_minute < 0 or trip.duration_from_clock_min <= 0):
            raise ValueError("BLOCKED_M2_TAXONOMY_OR_CLOCK")
        grouped[rid].append(trip)
    days: list[OriginalDay] = []
    people: set[str] = set()
    for raw in day_rows:
        rid = raw["row_id"]
        pid = raw["source_person_id"]
        hh = raw["source_household_id"]
        if pid in people:
            raise ValueError("BLOCKED_M2_PERSON_IDENTITY")
        people.add(pid)
        trips = sorted(grouped.pop(rid, []), key=lambda t: t.trip_index)
        n = int(raw["trip_count"])
        if (len(trips) != n or [t.trip_index for t in trips] != list(range(1, n + 1))
                or _flag(raw["trip_day"]) != bool(n)
                or not _flag(raw["temporal_chain_valid"])
                or not _flag(raw["distance_chain_valid"])):
            raise ValueError("BLOCKED_M2_DAY_CHAIN")
        last_activity = "HOME"
        last_arrival = -1
        for trip in trips:
            if (trip.row_id != rid or trip.person_id != pid or trip.household_id != hh
                    or trip.origin_activity != last_activity
                    or trip.departure_clock_minute < last_arrival):
                raise ValueError("BLOCKED_M2_ACTIVITY_CHAIN")
            last_activity = trip.destination_activity
            last_arrival = trip.arrival_absolute_minute
        returns = _flag(raw["return_home"])
        if (trips and (raw["final_activity"] != last_activity
                       or returns != (last_activity == "HOME"))):
            raise ValueError("BLOCKED_M2_FINAL_ACTIVITY")
        if not trips and str(raw["final_activity"]).lower() not in {"", "none", "nan"}:
            raise ValueError("BLOCKED_M2_NO_TRIP_FINAL")
        escort = any("ESCORT" in (t.origin_activity, t.destination_activity) for t in trips)
        days.append(OriginalDay(rid, pid, hh, tuple(trips), escort, returns))
    if grouped:
        raise ValueError("BLOCKED_M2_ORPHAN_TRIP")
    escort_days = [d for d in days if d.has_escort]
    escort_trips = sum(len(d.trips) for d in escort_days)
    events = sum(t.destination_activity == "ESCORT" for d in escort_days for t in d.trips)
    if strict and (len(days), len(trip_rows), len(escort_days), escort_trips, events) != (
            100000, 325613, 15381, 84862, 18871):
        raise ValueError("BLOCKED_M2_FROZEN_CARDINALITIES")
    return tuple(days)
