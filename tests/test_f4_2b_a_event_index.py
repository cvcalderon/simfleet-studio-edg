from __future__ import annotations

import csv
import gzip
from pathlib import Path

import pandas as pd  # type: ignore[import-untyped]
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


def test_exact_f4_2a_pandas_decimal_and_event_identity(tmp_path: Path) -> None:
    """F4.2a pandas parsing, not float(text), defines exact stable priors.

    Event identity, ordering and household priority must NOT be derived from
    pandas' potential dtype inference of identifier columns.
    """
    decimal = "27.66552206761079802"
    days = [{"row_id": "r02", "source_person_id": "person02",
             "source_household_id": "hh02", "trip_count": "3"},
            {"row_id": "r01", "source_person_id": "person01",
             "source_household_id": "hh01", "trip_count": "4"}]
    specifications = [
        ("r02", "person02", "hh02", "1", "HOME", "EDUCATION", "2.00000000000000000"),
        ("r01", "person01", "hh01", "1", "HOME", "WORK", decimal),
        ("r01", "person01", "hh01", "2", "WORK", "ESCORT", "4.4"),
        ("r02", "person02", "hh02", "2", "EDUCATION", "ESCORT", "3.1"),
        ("r01", "person01", "hh01", "3", "ESCORT", "WORK", "200.0"),
        ("r02", "person02", "hh02", "3", "ESCORT", "HOME", "2.0"),
        ("r01", "person01", "hh01", "4", "WORK", "ESCORT", "6.0"),
    ]
    trips = [{"row_id": r, "source_person_id": p, "source_household_id": hh,
              "trip_index": i, "origin_activity": orig, "destination_activity": dest,
              "distance_prior_km": prior, "arrival_absolute_minute": "180",
              "departure_clock_minute": "75"}
             for r, p, hh, i, orig, dest, prior in specifications]
    dpath, tpath = tmp_path / "d.csv.gz", tmp_path / "t.csv.gz"
    gz(dpath, days)
    gz(tpath, trips)
    # Deliberately reproduce the reference FULL dataframe read, not a
    # pandas options subset that could have different dtype inference.
    ref = pd.read_csv(tpath, low_memory=False)
    parsed = float(ref.loc[1, "distance_prior_km"])
    assert float(decimal) != parsed  # This fixture detects parser drift.

    result = index_frozen_m2(dpath, tpath, enforce_100k=False)
    assert result.stable_priors[("person01", "WORK")].hex() == parsed.hex()
    assert result.stable_priors[("person02", "EDUCATION")] == 2.0
    # Non-HOME incoming WORK=200 must not contaminate HOME-first median.
    assert result.activities["person01"] == frozenset({"WORK"})
    assert result.person_households == {"person01": "hh01", "person02": "hh02"}
    assert [(e.row_id, e.trip_index, e.person_id, e.household_id,
             e.arrival_absolute_minute, e.departure_clock_minute)
            for e in result.events] == [
        ("r01", 2, "person01", "hh01", 180, 75),
        ("r01", 4, "person01", "hh01", 180, 75),
        ("r02", 2, "person02", "hh02", 180, 75),
    ]
    assert (result.day_count, result.trip_count, result.escort_day_count,
            result.escort_day_trip_count) == (2, 7, 2, 7)


def test_home_first_median_reference_for_even_home_arrivals(tmp_path: Path) -> None:
    vals = ("20.61184845303565893", "27.66552206761079802")
    days = [{"row_id": "day", "source_person_id": "person", "source_household_id": "hh",
             "trip_count": "3"}]
    trips = [{"row_id": "day", "source_person_id": "person", "source_household_id": "hh",
              "trip_index": str(i), "origin_activity": origin, "destination_activity": "WORK",
              "distance_prior_km": value, "arrival_absolute_minute": "220",
              "departure_clock_minute": "80"}
             for i, (origin, value) in enumerate(zip(("HOME", "HOME", "WORK"),
                (*vals, "100.0"), strict=True), 1)]
    dpath, tpath = tmp_path / "day.csv.gz", tmp_path / "trip.csv.gz"
    gz(dpath, days)
    gz(tpath, trips)
    frame = pd.read_csv(tpath, low_memory=False)
    reference = float((float(frame.loc[0, "distance_prior_km"]) +
                       float(frame.loc[1, "distance_prior_km"])) / 2)
    result = index_frozen_m2(dpath, tpath, enforce_100k=False)
    assert result.stable_priors[("person", "WORK")].hex() == reference.hex()
    assert result.events == ()
