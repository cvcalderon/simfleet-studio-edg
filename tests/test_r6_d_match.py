from __future__ import annotations

import pandas as pd

from simfleet_edg.common.demand_match import (
    MATCH_PERSONDAY_COLUMNS,
    MATCH_TIERS,
    build_match_persondays,
    build_match_persondays_from_assignment_witness,
    build_match_trips,
    combined_bridge_sha256,
    match_tier_summary,
)


def _persons() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "person_id": "P_1",
                "household_id": "HH_1",
                "home_zone_id": 1100101,
                "source_person_id": 101.0,
                "age_infr_class": "07_25_39",
                "sex": "MALE",
                "primary_activity_status": "EMPLOYED",
                "employment_participation": "EMPLOYED",
            },
            {
                "person_id": "P_2",
                "household_id": "HH_2",
                "home_zone_id": 1100102,
                "source_person_id": float("nan"),
                "age_infr_class": "07_25_39",
                "sex": "FEMALE",
                "primary_activity_status": "EMPLOYED",
                "employment_participation": "EMPLOYED",
            },
        ]
    )


def _households() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"household_id": "HH_1", "materialized_member_count": 1},
            {"household_id": "HH_2", "materialized_member_count": 2},
        ]
    )


def _donors() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "HP_ID": 101,
                "H_ID_num": 100,
                "P_ID": 1,
                "age_infr_class": "07_25_39",
                "sex": "MALE",
                "primary_activity_status": "EMPLOYED",
                "employment_participation": "EMPLOYED",
                "household_size_class": 1,
                "mobil_diff": 1,
                "analytic_total_trip_count": 2.0,
                "replay_complete_zero": False,
                "replay_complete_mobile": True,
                "P_GEW": 1.0,
            },
            {
                "HP_ID": 102,
                "H_ID_num": 200,
                "P_ID": 1,
                "age_infr_class": "07_25_39",
                "sex": "MALE",
                "primary_activity_status": "EMPLOYED",
                "employment_participation": "EMPLOYED",
                "household_size_class": 2,
                "mobil_diff": 1,
                "analytic_total_trip_count": 1.0,
                "replay_complete_zero": False,
                "replay_complete_mobile": True,
                "P_GEW": 2.0,
            },
            {
                "HP_ID": 103,
                "H_ID_num": 300,
                "P_ID": 1,
                "age_infr_class": "07_25_39",
                "sex": "FEMALE",
                "primary_activity_status": "EMPLOYED",
                "employment_participation": "EMPLOYED",
                "household_size_class": 2,
                "mobil_diff": 0,
                "analytic_total_trip_count": 0.0,
                "replay_complete_zero": True,
                "replay_complete_mobile": False,
                "P_GEW": 3.0,
            },
        ]
    )


def _raw() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"HP_ID": 101, "H_ID": 100, "P_ID": 1, "P_GEW": 1.0, "ST_MONAT": 3, "ST_JAHR": 2017, "ST_WOTAG": 4, "ST_WOCHE": 12, "feiertag": 0, "saison": 2, "mobil_diff": 1, "HP_SEX": 1, "HP_ALTER": 35, "HP_TAET": 1, "H_GR": 1},
            {"HP_ID": 102, "H_ID": 200, "P_ID": 1, "P_GEW": 2.0, "ST_MONAT": 3, "ST_JAHR": 2017, "ST_WOTAG": 4, "ST_WOCHE": 12, "feiertag": 0, "saison": 2, "mobil_diff": 1, "HP_SEX": 1, "HP_ALTER": 35, "HP_TAET": 1, "H_GR": 2},
            {"HP_ID": 103, "H_ID": 300, "P_ID": 1, "P_GEW": 3.0, "ST_MONAT": 3, "ST_JAHR": 2017, "ST_WOTAG": 4, "ST_WOCHE": 12, "feiertag": 0, "saison": 2, "mobil_diff": 0, "HP_SEX": 2, "HP_ALTER": 35, "HP_TAET": 1, "H_GR": 2},
        ]
    )


def _evidence() -> dict[str, pd.DataFrame]:
    coverage = pd.DataFrame(
        [
            {"HP_ID": 101, "analytic_total_trip_count": 2.0, "chain_coverage_status": "DIRECT_REPORTED_CHAIN_COMPLETE"},
            {"HP_ID": 102, "analytic_total_trip_count": 1.0, "chain_coverage_status": "DIRECT_REPORTED_CHAIN_COMPLETE"},
            {"HP_ID": 103, "analytic_total_trip_count": 0.0, "chain_coverage_status": "ZERO_TRIP_COMPLETE"},
        ]
    )
    functional = pd.DataFrame(
        [
            {"HP_ID": 101, "full_functional_day_sequence_eligible": True},
            {"HP_ID": 102, "full_functional_day_sequence_eligible": True},
            {"HP_ID": 103, "full_functional_day_sequence_eligible": False},
        ]
    )
    temporal = pd.DataFrame(
        [
            {"HP_ID": 101, "temporal_sequence_fit_eligible": True},
            {"HP_ID": 102, "temporal_sequence_fit_eligible": True},
            {"HP_ID": 103, "temporal_sequence_fit_eligible": False},
        ]
    )
    transition = pd.DataFrame(
        [
            {"HP_ID": 101, "W_ID": 1, "W_RBW": 0, "canonical_trip_purpose": "WORK_COMMUTE", "origin_activity": "HOME", "destination_activity": "WORK", "destination_resolution": "DIRECT_FROM_W_ZWECK"},
            {"HP_ID": 101, "W_ID": 2, "W_RBW": 0, "canonical_trip_purpose": "RETURN_HOME", "origin_activity": "WORK", "destination_activity": "HOME", "destination_resolution": "DIRECT_FROM_W_ZWECK"},
            {"HP_ID": 102, "W_ID": 1, "W_RBW": 0, "canonical_trip_purpose": "WORK_COMMUTE", "origin_activity": "HOME", "destination_activity": "WORK", "destination_resolution": "DIRECT_FROM_W_ZWECK"},
        ]
    )
    trip_time = pd.DataFrame(
        [
            {"HP_ID": 101, "W_ID": 1, "W_RBW": 0, "departure_clock_minute": 480.0, "arrival_clock_minute": 500.0, "arrival_day_offset": 0.0, "duration_from_clock_min": 20.0, "temporal_row_status": "DIRECT_TEMPORAL_VALID"},
            {"HP_ID": 101, "W_ID": 2, "W_RBW": 0, "departure_clock_minute": 1020.0, "arrival_clock_minute": 1040.0, "arrival_day_offset": 0.0, "duration_from_clock_min": 20.0, "temporal_row_status": "DIRECT_TEMPORAL_VALID"},
            {"HP_ID": 102, "W_ID": 1, "W_RBW": 0, "departure_clock_minute": 480.0, "arrival_clock_minute": 510.0, "arrival_day_offset": 0.0, "duration_from_clock_min": 30.0, "temporal_row_status": "DIRECT_TEMPORAL_VALID"},
        ]
    )
    spatial = pd.DataFrame(
        [
            {"HP_ID": 101, "W_ID": 1, "W_RBW": 0, "wegkm": 3.5, "wegkm_imp": 3.5, "source_distance_status": "DIRECT_SOURCE_DISTANCE_VALID"},
            {"HP_ID": 101, "W_ID": 2, "W_RBW": 0, "wegkm": 70703.0, "wegkm_imp": 4.0, "source_distance_status": "DIRECT_NO_DETAIL_DISTANCE_IMPUTED"},
            {"HP_ID": 102, "W_ID": 1, "W_RBW": 0, "wegkm": 5.0, "wegkm_imp": 5.0, "source_distance_status": "DIRECT_SOURCE_DISTANCE_VALID"},
        ]
    )
    return {
        "coverage": coverage,
        "functional": functional,
        "temporal_sequence": temporal,
        "transition": transition,
        "trip_time": trip_time,
        "spatial": spatial,
    }


def test_matching_excludes_self_and_relaxes_to_next_tier() -> None:
    result = build_match_persondays(
        population_persons=_persons(),
        population_households=_households(),
        donor_pool=_donors(),
        raw_persons=_raw(),
        evidence=_evidence(),
        seed=20260924,
    )
    assert list(result.columns) == MATCH_PERSONDAY_COLUMNS
    first = result.iloc[0]
    assert int(first["diary_source_hp_id"]) == 102
    assert first["match_tier"] == "T2_RELAX_HHSIZE"
    assert bool(first["relaxed_due_to_self_only"])
    assert not bool(first["self_diary_match"])


def test_matching_is_deterministic_for_fixed_seed() -> None:
    kwargs = {
        "population_persons": _persons(),
        "population_households": _households(),
        "donor_pool": _donors(),
        "raw_persons": _raw(),
        "evidence": _evidence(),
        "seed": 20260924,
    }
    first = build_match_persondays(**kwargs)
    second = build_match_persondays(**kwargs)
    pd.testing.assert_frame_equal(first, second)


def test_zero_trip_matched_day_emits_no_trip_rows() -> None:
    persondays = build_match_persondays(
        population_persons=_persons(),
        population_households=_households(),
        donor_pool=_donors(),
        raw_persons=_raw(),
        evidence=_evidence(),
        seed=20260924,
    )
    trips = build_match_trips(persondays, _evidence())
    zero_ids = set(persondays.loc[persondays["plan_status"] == "COMPLETE_ZERO_TRIP", "person_day_id"])
    assert not zero_ids.intersection(set(trips["person_day_id"]))
    assert trips["mode_status"].eq("NOT_AVAILABLE_M2").all()
    assert trips["spatial_realization_status"].eq("NOT_REALIZED_M2_ONLY").all()


def test_match_tier_summary_uses_frozen_order() -> None:
    frame = pd.DataFrame(
        {"match_tier": ["T4_AGE_SEX", "T1_EXACT_AGE_SEX_ACTIVITY_HHSIZE"]}
    )
    summary = match_tier_summary(frame)
    assert summary["match_tier"].tolist()[:5] == [tier for tier, _ in MATCH_TIERS]
    assert int(summary.iloc[0]["n"]) == 1
    assert int(summary.loc[summary["match_tier"] == "T4_AGE_SEX", "n"].iloc[0]) == 1


def test_bridge_hash_algorithm_is_order_sensitive() -> None:
    one = combined_bridge_sha256("a", "b", "c", "d")
    two = combined_bridge_sha256("a", "c", "b", "d")
    assert one != two


def test_assignment_witness_reconstructs_declared_donors() -> None:
    witness = pd.DataFrame(
        [
            {"generated_person_id": "P_1", "diary_source_hp_id": 102},
            {"generated_person_id": "P_2", "diary_source_hp_id": 103},
        ]
    )
    result = build_match_persondays_from_assignment_witness(
        population_persons=_persons(),
        population_households=_households(),
        donor_pool=_donors(),
        raw_persons=_raw(),
        evidence=_evidence(),
        assignment_witness=witness,
    )
    assert result["diary_source_hp_id"].astype(int).tolist() == [102, 103]
    assert result["match_tier"].tolist() == ["T2_RELAX_HHSIZE", "T1_EXACT_AGE_SEX_ACTIVITY_HHSIZE"]
    assert result["plan_status"].tolist() == ["COMPLETE_MOBILE_DAY", "COMPLETE_ZERO_TRIP"]
    assert result["source_season"].tolist() == [2, 2]


def test_assignment_witness_rejects_self_match() -> None:
    witness = pd.DataFrame(
        [
            {"generated_person_id": "P_1", "diary_source_hp_id": 101},
            {"generated_person_id": "P_2", "diary_source_hp_id": 103},
        ]
    )
    try:
        build_match_persondays_from_assignment_witness(
            population_persons=_persons(),
            population_households=_households(),
            donor_pool=_donors(),
            raw_persons=_raw(),
            evidence=_evidence(),
            assignment_witness=witness,
        )
    except ValueError as exc:
        assert "not valid" in str(exc)
    else:
        raise AssertionError("self-match witness must be rejected")
