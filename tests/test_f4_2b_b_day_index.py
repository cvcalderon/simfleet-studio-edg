"""Frozen M2 identities, stable order, and fatal chain violations."""
from __future__ import annotations

import csv
import gzip
from pathlib import Path

import pytest

from simfleet_edg.spatial.escort_partial_day_index import load_original_days


def _gz(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "wt", encoding="utf-8", newline="") as out:
        writer = csv.DictWriter(out, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def _fixture(tmp_path: Path) -> None:
    d = {"row_id": "d1", "source_person_id": "p1", "source_household_id": "h1",
         "trip_count": "2", "trip_day": "True", "temporal_chain_valid": "True",
         "distance_chain_valid": "True", "return_home": "True", "final_activity": "HOME"}
    t = {"row_id": "d1", "source_person_id": "p1", "source_household_id": "h1",
         "trip_index": "1", "origin_activity": "HOME", "destination_activity": "ESCORT",
         "departure_clock_minute": "400", "arrival_absolute_minute": "410",
         "duration_from_clock_min": "10", "distance_prior_km": "1.25"}
    u = {**t, "trip_index": "2", "origin_activity": "ESCORT", "destination_activity": "HOME",
         "departure_clock_minute": "420", "arrival_absolute_minute": "430"}
    _gz(tmp_path / "dgen_A/dgen_day_rows_v1.csv.gz", [d])
    _gz(tmp_path / "dgen_A/dgen_trip_rows_v1.csv.gz", [t, u])


def test_escort_day_loaded_without_generator(tmp_path: Path) -> None:
    _fixture(tmp_path)
    days = load_original_days(tmp_path, strict=False)
    assert len(days) == 1 and days[0].has_escort
    assert [t.trip_index for t in days[0].trips] == [1, 2]
    assert days[0].trips[1].origin_activity == "ESCORT"


def test_m2_discontinuity_is_global_blocker(tmp_path: Path) -> None:
    _fixture(tmp_path)
    path = tmp_path / "dgen_A/dgen_trip_rows_v1.csv.gz"
    with gzip.open(path, "rt", newline="", encoding="utf-8") as stream:
        data = list(csv.DictReader(stream))
    data[1]["origin_activity"] = "SHOPPING"
    _gz(path, data)
    with pytest.raises(ValueError, match="BLOCKED_M2_ACTIVITY_CHAIN"):
        load_original_days(tmp_path, strict=False)
