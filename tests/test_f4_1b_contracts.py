import pandas as pd
import pytest

from simfleet_edg.canonical.mobility import (
    ActivityIntent,
    LocationRef,
    LocationSupplyRecord,
    TripDemand,
)
from simfleet_edg.demand.m2_m3_adapter import adapt_joint_generated_frames


def _frames():
    days = pd.DataFrame(
        [
            {
                "pipeline": "SELECTED",
                "replicate_index": 0,
                "row_id": "D1",
                "source_household_id": "H1",
                "source_person_id": "P1",
                "trip_day": True,
                "trip_count": 2,
                "final_activity": "HOME",
                "return_home": True,
                "temporal_chain_valid": True,
                "distance_chain_valid": True,
            },
            {
                "pipeline": "SELECTED",
                "replicate_index": 0,
                "row_id": "D2",
                "source_household_id": "H2",
                "source_person_id": "P2",
                "trip_day": False,
                "trip_count": 0,
                "final_activity": "",
                "return_home": False,
                "temporal_chain_valid": True,
                "distance_chain_valid": True,
            },
        ]
    )
    trips = pd.DataFrame(
        [
            {
                "pipeline": "SELECTED",
                "replicate_index": 0,
                "row_id": "D1",
                "source_household_id": "H1",
                "source_person_id": "P1",
                "trip_index": 1,
                "trip_count": 2,
                "origin_activity": "HOME",
                "destination_activity": "WORK",
                "departure_clock_minute": 480,
                "arrival_absolute_minute": 510,
                "duration_from_clock_min": 30,
                "distance_prior_km": 8.0,
            },
            {
                "pipeline": "SELECTED",
                "replicate_index": 0,
                "row_id": "D1",
                "source_household_id": "H1",
                "source_person_id": "P1",
                "trip_index": 2,
                "trip_count": 2,
                "origin_activity": "WORK",
                "destination_activity": "HOME",
                "departure_clock_minute": 1020,
                "arrival_absolute_minute": 1055,
                "duration_from_clock_min": 35,
                "distance_prior_km": 8.4,
            },
        ]
    )
    return days, trips


def test_adapter_builds_person_day_plans():
    days, trips = _frames()
    plans = adapt_joint_generated_frames(days, trips)
    assert len(plans) == 2
    mobile = plans[0]
    assert mobile.person_id == "P1"
    assert mobile.household_id == "H1"
    assert len(mobile.trips) == 2
    assert [x.activity for x in mobile.activities] == ["HOME", "WORK", "HOME"]
    assert mobile.return_home is True
    assert plans[1].trips == ()
    assert plans[1].activities == ()


def test_adapter_rejects_target_leakage():
    days, trips = _frames()
    trips["target_distance_prior_km"] = 9.0
    with pytest.raises(ValueError, match="forbidden"):
        adapt_joint_generated_frames(days, trips)


def test_adapter_rejects_chain_discontinuity():
    days, trips = _frames()
    trips.loc[trips["trip_index"].eq(2), "origin_activity"] = "SHOPPING"
    with pytest.raises(ValueError, match="discontinuity"):
        adapt_joint_generated_frames(days, trips)


def test_adapter_rejects_trip_count_mismatch():
    days, trips = _frames()
    days.loc[days["row_id"].eq("D1"), "trip_count"] = 3
    with pytest.raises(ValueError, match="Trip count mismatch"):
        adapt_joint_generated_frames(days, trips)


def test_adapter_rejects_temporal_discontinuity():
    days, trips = _frames()
    trips.loc[trips["trip_index"].eq(2), "departure_clock_minute"] = 500
    with pytest.raises(ValueError, match="Temporal-chain discontinuity"):
        adapt_joint_generated_frames(days, trips)


def test_trip_demand_requires_positive_finite_distance():
    with pytest.raises(ValueError, match="distance_prior_km"):
        TripDemand(1, "HOME", "WORK", 480, 500, 20, 0.0)


def test_activity_intent_validates_clock():
    with pytest.raises(ValueError, match="departure_clock_minute"):
        ActivityIntent(0, "HOME", None, 1440)


def test_location_ref_requires_finite_coordinates():
    with pytest.raises(ValueError, match="finite"):
        LocationRef("L1", "PLR", float("nan"), 52.5)


def test_supply_keeps_eligibility_attractiveness_capacity_separate():
    location = LocationRef("L1", "POI", 13.4, 52.5)
    record = LocationSupplyRecord(
        location=location,
        eligible_purposes=("WORK",),
        attractiveness=2.0,
        capacity=10.0,
        provenance="TEST_FIXTURE",
    )
    assert record.eligible_purposes == ("WORK",)
    assert record.attractiveness == 2.0
    assert record.capacity == 10.0


def test_nonselected_pipeline_is_ignored():
    days, trips = _frames()
    other_days = days.copy()
    other_days["pipeline"] = "ALL_REFERENCE"
    other_trips = trips.copy()
    other_trips["pipeline"] = "ALL_REFERENCE"
    plans = adapt_joint_generated_frames(
        pd.concat([days, other_days], ignore_index=True),
        pd.concat([trips, other_trips], ignore_index=True),
    )
    assert len(plans) == 2
    assert all(plan.pipeline == "SELECTED" for plan in plans)
