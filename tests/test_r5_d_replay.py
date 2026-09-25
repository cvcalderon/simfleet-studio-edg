from __future__ import annotations

import pandas as pd

from simfleet_edg.common.demand_replay import (
    DAY_STATUS,
    PERSONDAY_COLUMNS,
    TRIP_COLUMNS,
    build_replay_persondays,
    build_replay_trips,
    replay_assignment_summary,
    strict_train_source_persons,
)


def _evidence() -> dict[str, pd.DataFrame]:
    return {
        "coverage": pd.DataFrame(
            [
                {"HP_ID": 101, "analytic_total_trip_count": 2.0, "chain_coverage_status": "DIRECT_REPORTED_CHAIN_COMPLETE"},
                {"HP_ID": 102, "analytic_total_trip_count": 1.0, "chain_coverage_status": "DIRECT_REPORTED_CHAIN_COMPLETE"},
            ]
        ),
        "functional": pd.DataFrame(
            [
                {"HP_ID": 101, "full_functional_day_sequence_eligible": True},
                {"HP_ID": 102, "full_functional_day_sequence_eligible": False},
            ]
        ),
        "temporal_sequence": pd.DataFrame(
            [
                {"HP_ID": 101, "temporal_sequence_fit_eligible": True},
                {"HP_ID": 102, "temporal_sequence_fit_eligible": True},
            ]
        ),
        "transition": pd.DataFrame(
            [
                {"HP_ID": 101, "W_ID": 1, "W_RBW": 0, "canonical_trip_purpose": "WORK_COMMUTE", "origin_activity": "HOME", "destination_activity": "WORK", "destination_resolution": "DIRECT_FROM_W_ZWECK"},
                {"HP_ID": 101, "W_ID": 2, "W_RBW": 0, "canonical_trip_purpose": "RETURN_HOME", "origin_activity": "WORK", "destination_activity": "HOME", "destination_resolution": "DIRECT_FROM_W_ZWECK"},
            ]
        ),
        "trip_time": pd.DataFrame(
            [
                {"HP_ID": 101, "W_ID": 1, "W_RBW": 0, "departure_clock_minute": 480.0, "arrival_clock_minute": 500.0, "arrival_day_offset": 0.0, "duration_from_clock_min": 20.0, "temporal_row_status": "DIRECT_TEMPORAL_VALID"},
                {"HP_ID": 101, "W_ID": 2, "W_RBW": 0, "departure_clock_minute": 1020.0, "arrival_clock_minute": 1040.0, "arrival_day_offset": 0.0, "duration_from_clock_min": 20.0, "temporal_row_status": "DIRECT_TEMPORAL_VALID"},
            ]
        ),
        "spatial": pd.DataFrame(
            [
                {"HP_ID": 101, "W_ID": 1, "W_RBW": 0, "wegkm": 3.5, "wegkm_imp": 3.5, "source_distance_status": "DIRECT_SOURCE_DISTANCE_VALID"},
                {"HP_ID": 101, "W_ID": 2, "W_RBW": 0, "wegkm": 70703.0, "wegkm_imp": 4.0, "source_distance_status": "DIRECT_NO_DETAIL_DISTANCE_IMPUTED"},
            ]
        ),
    }


def _raw() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"HP_ID": 101, "H_ID": 100, "P_ID": 1, "P_GEW": 2.0, "ST_MONAT": 3, "ST_JAHR": 2017, "ST_WOTAG": 4, "ST_WOCHE": 12, "feiertag": 0, "saison": 2, "mobil_diff": 1, "HP_SEX": 1, "HP_ALTER": 35, "HP_TAET": 1, "H_GR": 1},
            {"HP_ID": 102, "H_ID": 200, "P_ID": 2, "P_GEW": 3.0, "ST_MONAT": 4, "ST_JAHR": 2017, "ST_WOTAG": 5, "ST_WOCHE": 14, "feiertag": 0, "saison": 2, "mobil_diff": 1, "HP_SEX": 2, "HP_ALTER": 30, "HP_TAET": 10, "H_GR": 2},
        ]
    )


def test_day_status_preserves_trip_day_unreported_semantics() -> None:
    assert DAY_STATUS[5] == ("TRIP_DAY_UNREPORTED", "TRIP_DAY")
    assert DAY_STATUS[0] == ("NO_TRIP_CONFIRMED", "NO_TRIP")


def test_personday_replay_never_substitutes_roster_only_person() -> None:
    population = pd.DataFrame(
        [
            {"person_id": "P_1", "household_id": "HH_1", "home_zone_id": 1100101, "source_person_id": 101.0},
            {"person_id": "P_2", "household_id": "HH_2", "home_zone_id": 1100102, "source_person_id": float("nan")},
        ]
    )
    result = build_replay_persondays(population, _raw(), _evidence())
    assert list(result.columns) == PERSONDAY_COLUMNS
    assert result.loc[0, "assignment_status"] == "COMPLETE_MOBILE_DAY"
    assert result.loc[1, "assignment_status"] == "UNAVAILABLE_NO_PERSONDAY"
    assert pd.isna(result.loc[1, "diary_source_hp_id"])
    assert result.loc[1, "matching_features"] == "NONE_REQUIRED"


def test_incomplete_functional_chain_is_not_repaired() -> None:
    population = pd.DataFrame(
        [{"person_id": "P_2", "household_id": "HH_2", "home_zone_id": 1100102, "source_person_id": 102.0}]
    )
    result = build_replay_persondays(population, _raw(), _evidence())
    assert result.loc[0, "assignment_status"] == "PARTIAL_COUNT_OR_CHAIN_ONLY"
    assert result.loc[0, "plan_status"] == "INCOMPLETE"


def test_trip_materialization_uses_raw_then_imputed_distance() -> None:
    population = pd.DataFrame(
        [{"person_id": "P_1", "household_id": "HH_1", "home_zone_id": 1100101, "source_person_id": 101.0}]
    )
    persondays = build_replay_persondays(population, _raw(), _evidence())
    trips = build_replay_trips(persondays, _evidence())
    assert list(trips.columns) == TRIP_COLUMNS
    assert len(trips) == 2
    assert trips["distance_prior_km"].tolist() == [3.5, 4.0]
    assert trips["distance_prior_provenance"].tolist() == [
        "OBSERVED_SOURCE_PATH_LENGTH",
        "SOURCE_IMPUTED_PATH_LENGTH_DIAGNOSTIC",
    ]
    assert trips["mode_status"].eq("NOT_AVAILABLE_M2").all()


def test_strict_train_source_pool_uses_household_split() -> None:
    split = pd.DataFrame(
        [
            {"source_household_id": 100, "split": "TRAIN", "joint_rmin_donor_eligible": True},
            {"source_household_id": 200, "split": "CALIBRATION", "joint_rmin_donor_eligible": True},
        ]
    )
    result = strict_train_source_persons(split, _raw())
    assert result["HP_ID"].tolist() == [101]


def test_assignment_summary_has_frozen_order() -> None:
    frame = pd.DataFrame(
        {"assignment_status": ["COMPLETE_ZERO_TRIP", "COMPLETE_MOBILE_DAY", "COMPLETE_MOBILE_DAY"]}
    )
    summary = replay_assignment_summary(frame)
    assert summary.iloc[0]["assignment_status"] == "COMPLETE_MOBILE_DAY"
    assert int(summary.iloc[0]["n"]) == 2
    assert summary.iloc[3]["assignment_status"] == "COMPLETE_ZERO_TRIP"
