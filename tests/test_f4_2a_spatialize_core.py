from __future__ import annotations

import pytest
from pyproj import Transformer

from simfleet_edg.canonical.mobility import (
    ActivityIntent,
    LocationRef,
    PersonDayPlan,
    ResidentialAnchor,
    TripDemand,
)
from simfleet_edg.spatial.candidate_index import Candidate, CandidateIndex
from simfleet_edg.spatial.spatialize_core import Spatializer


def _location(name: str, x: float, y: float) -> LocationRef:
    transform = Transformer.from_crs("EPSG:25833", "EPSG:4326", always_xy=True)
    lon, lat = transform.transform(x, y)
    return LocationRef(name, "TEST", lon, lat)


def _trip(i: int, src: str, dst: str, km: float = 1.0) -> TripDemand:
    return TripDemand(i, src, dst, 100 * i, 100 * i + 30, 30, km)


def _day(person: str, household: str, trips: tuple[TripDemand, ...]) -> PersonDayPlan:
    activities = (tuple(ActivityIntent(i, a, None, None) for i, a in enumerate(
        [trips[0].origin_activity] + [t.destination_activity for t in trips])) if trips else ())
    return PersonDayPlan(person, household, person + "_day", "SELECTED", 0,
                         bool(trips), trips, activities, True, True, True)


def _builder() -> tuple[Spatializer, ResidentialAnchor]:
    home = _location("home", 390000, 5810000)
    work = _location("work", 391000, 5810000)
    shop = _location("shop", 391000, 5811000)
    anchor = ResidentialAnchor("hh", home, "11000000000000", "FROZEN")
    return Spatializer({"WORK_COMMUTE": CandidateIndex([Candidate("work", 391000, 5810000)]),
        "SHOPPING": CandidateIndex([Candidate("shop", 391000, 5811000)])},
        {"home": home, "work": work, "shop": shop}, {"hh": anchor}), anchor


def test_stable_work_and_home_reuse_and_continuity() -> None:
    spatializer, anchor = _builder()
    plan = _day("p", "hh", (_trip(1, "HOME", "WORK"),
                             _trip(2, "WORK", "SHOPPING"),
                             _trip(3, "SHOPPING", "WORK"),
                             _trip(4, "WORK", "HOME")))
    result = spatializer.spatialize((plan,), "S_DIST")
    trips = result.days[0].trips
    assert [t.destination.location_id for t in trips] == ["work", "shop", "work", "home"]
    assert all(trips[i].destination == trips[i + 1].origin for i in range(len(trips) - 1))
    assert result.days[0].home_anchor is anchor
    assert len(result.stable_locations) == 1
    assert result.stable_locations[0].prior_aggregate_km == 1.0


def test_home_only_no_trip_and_escort_full_day_exclusion() -> None:
    spatializer, _ = _builder()
    no_trip = _day("inactive", "hh", ())
    escort = _day("escort", "hh", (_trip(1, "HOME", "ESCORT"),
                                   _trip(2, "ESCORT", "HOME")))
    result = spatializer.spatialize((no_trip, escort), "S_NEAR")
    assert len(result.days) == 1 and result.days[0].trips == ()
    assert len(result.exclusions) == 1 and result.exclusions[0].person_id == "escort"


def test_non_home_first_origin_is_a_main_blocker() -> None:
    spatializer, _ = _builder()
    with pytest.raises(ValueError, match="MAIN_BLOCKER_INITIAL_NON_HOME"):
        spatializer.spatialize((_day("bad", "hh", (_trip(1, "WORK", "HOME"),)),), "S_DIST")
