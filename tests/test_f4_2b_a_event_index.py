from __future__ import annotations

import csv
import gzip
from pathlib import Path

import pytest

from simfleet_edg.spatial.escort_event_index import index_frozen_m2


def gz(path: Path, rows: list[dict[str, str]]) -> None:
    with gzip.open(path, "wt", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def test_escort_occurrences_and_home_first_median(tmp_path: Path) -> None:
    day = [{"row_id": "r1", "source_person_id": "a", "source_household_id": "h1", "trip_count": "3"},
           {"row_id": "r2", "source_person_id": "b", "source_household_id": "h2", "trip_count": "2"}]
    trips = [{"row_id": "r1", "source_person_id": "a", "source_household_id": "h1",
              "trip_index": str(i), "origin_activity": origin, "destination_activity": dest,
              "distance_prior_km": str(km), "arrival_absolute_minute": "120", "departure_clock_minute": "60"}
             for i, (origin, dest, km) in enumerate((("HOME", "WORK", 4),
                ("WORK", "ESCORT", 2), ("ESCORT", "WORK", 30)), start=1)]
    trips += [{"row_id": "r2", "source_person_id": "b", "source_household_id": "h2",
               "trip_index": str(i), "origin_activity": origin, "destination_activity": dest,
               "distance_prior_km": "5", "arrival_absolute_minute": "120", "departure_clock_minute": "60"}
              for i, (origin, dest) in enumerate((("HOME", "EDUCATION"), ("EDUCATION", "HOME")), 1)]
    gz(tmp_path / "d.csv.gz", day)
    gz(tmp_path / "t.csv.gz", trips)
    index = index_frozen_m2(tmp_path / "d.csv.gz", tmp_path / "t.csv.gz", enforce_100k=False)
    assert len(index.events) == 1
    assert index.events[0].event_id == "r1:2"
    assert index.stable_priors[("a", "WORK")] == 4.0
    assert index.activities["b"] == frozenset({"EDUCATION"})
    assert index.escort_day_count == 1
    assert index.escort_day_trip_count == 3
    with pytest.raises(ValueError, match="cardinalities"):
        index_frozen_m2(tmp_path / "d.csv.gz", tmp_path / "t.csv.gz")
