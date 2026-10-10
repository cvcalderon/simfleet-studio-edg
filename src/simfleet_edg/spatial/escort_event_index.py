"""Index already-generated full M2 without re-running D_GEN or modifying CORE."""
from __future__ import annotations

import csv
import gzip
import statistics
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

import pandas as pd  # type: ignore[import-untyped]


@dataclass(frozen=True)
class EscortEvent:
    row_id: str
    trip_index: int
    person_id: str
    household_id: str
    arrival_absolute_minute: int
    departure_clock_minute: int
    original_destination_activity: str = "ESCORT"

    @property
    def event_id(self) -> str:
        return f"{self.row_id}:{self.trip_index}"


@dataclass(frozen=True)
class M2Index:
    events: tuple[EscortEvent, ...]
    person_households: dict[str, str]
    # Frozen M2 persons with at least one supported target activity.
    activities: dict[str, frozenset[str]]
    # (person, purpose): exact F4.2a stable prior, HOME-origin first, median.
    stable_priors: dict[tuple[str, str], float]
    day_count: int
    trip_count: int
    escort_day_count: int
    escort_day_trip_count: int


def _rows(path: Path) -> list[dict[str, str]]:
    with gzip.open(path, "rt", encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def index_frozen_m2(day_path: Path, trip_path: Path, *, enforce_100k: bool = True) -> M2Index:
    """One trip scan; activity occurrences count once per destination ESCORT."""
    days = _rows(day_path)
    trips = _rows(trip_path)
    # F4.2a used the full pandas parser (low_memory=False) before adapting M2.
    # Keep stdlib CSV for EVERY original identity/event field and ordering;
    # use pandas only for the same IEEE-754 float conversion as frozen CORE.
    reference_trips = pd.read_csv(trip_path, low_memory=False)
    if len(reference_trips) != len(trips) or "distance_prior_km" not in reference_trips:
        raise ValueError("Frozen M2 pandas/CSV trip source misalignment")
    distance_priors = reference_trips["distance_prior_km"].to_numpy()
    if not days or len({d["row_id"] for d in days}) != len(days):
        raise ValueError("Frozen M2 day identity duplicate/empty")
    if len({(t["row_id"], int(t["trip_index"])) for t in trips}) != len(trips):
        raise ValueError("Frozen M2 trip identity duplicate")
    days_by_row = {d["row_id"]: d for d in days}
    households: dict[str, str] = {}
    for d in days:
        pid = d["source_person_id"]
        if pid in households:
            raise ValueError("Expected single frozen day per M1 person")
        households[pid] = d["source_household_id"]
    trip_counts: dict[str, int] = defaultdict(int)
    escort_rows: set[str] = set()
    incoming: dict[tuple[str, str], list[tuple[bool, float]]] = defaultdict(list)
    activity: dict[str, set[str]] = defaultdict(set)
    events: list[EscortEvent] = []
    for trip, numeric_prior in zip(trips, distance_priors, strict=True):
        row_id = trip["row_id"]
        day = days_by_row.get(row_id)
        if day is None or (day["source_person_id"] != trip["source_person_id"]
                           or day["source_household_id"] != trip["source_household_id"]):
            raise ValueError("M2 trip has orphan/mismatching day identity")
        trip_counts[row_id] += 1
        pid = trip["source_person_id"]
        dest = trip["destination_activity"]
        orig = trip["origin_activity"]
        if dest in ("EDUCATION", "WORK"):
            value = float(numeric_prior)
            if value <= 0:
                raise ValueError("Non-positive distance prior")
            incoming[(pid, dest)].append((orig == "HOME", value))
            activity[pid].add(dest)
        if dest == "ESCORT" or orig == "ESCORT":
            escort_rows.add(row_id)
        if dest == "ESCORT":
            events.append(EscortEvent(row_id, int(trip["trip_index"]), pid,
                                      trip["source_household_id"],
                                      int(trip["arrival_absolute_minute"]),
                                      int(trip["departure_clock_minute"])))
    for d in days:
        if trip_counts[d["row_id"]] != int(d["trip_count"]):
            raise ValueError("Frozen M2 trip count mismatch")
    priors = {}
    for key, choices in incoming.items():
        home = [p for is_home, p in choices if is_home]
        priors[key] = float(statistics.median(home or [p for _, p in choices]))
    events.sort(key=lambda e: (e.row_id, e.trip_index))
    excluded_trips = sum(trip_counts[row] for row in escort_rows)
    if enforce_100k and (len(days), len(trips), len(events), len(escort_rows),
                         excluded_trips) != (100000, 325613, 18871, 15381, 84862):
        raise ValueError("Frozen M2 cardinalities diverge from MAIN PREOPEN")
    return M2Index(tuple(events), households,
                   {p: frozenset(v) for p, v in activity.items()}, priors,
                   len(days), len(trips), len(escort_rows), excluded_trips)
