"""Deterministic reconstruction of the frozen F2.1 D_REPLAY diagnostic lane."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from simfleet_edg.common.population_materializer import age_infr_class, load_activity_recoding

DAY_STATUS = {
    0: ("NO_TRIP_CONFIRMED", "NO_TRIP"),
    1: ("TRIP_DAY_DETAILED", "TRIP_DAY"),
    2: ("TRIP_DAY_RBW_ONLY", "TRIP_DAY"),
    3: ("TRIP_DAY_DETAILED_PLUS_RBW", "TRIP_DAY"),
    4: ("MOBILE_FAR_ABROAD", "OUT_OF_SCOPE_DAY"),
    5: ("TRIP_DAY_UNREPORTED", "TRIP_DAY"),
    6: ("NO_TRIP_REPORTING_RISK", "NO_TRIP_UNCERTAIN"),
    9: ("MOBILITY_UNKNOWN", "UNKNOWN"),
}

PERSONDAY_COLUMNS = [
    "diagnostic_variant",
    "person_day_id",
    "generated_person_id",
    "generated_household_id",
    "generated_home_zone_id",
    "diary_source_hp_id",
    "diary_source_household_id",
    "diary_source_split",
    "assignment_status",
    "plan_status",
    "day_mobility_status",
    "participation_class",
    "analytic_total_trip_count",
    "chain_coverage_status",
    "full_functional_day_sequence_eligible",
    "temporal_sequence_fit_eligible",
    "survey_year",
    "survey_month",
    "survey_calendar_week",
    "survey_weekday",
    "source_holiday",
    "source_season",
    "diary_person_weight",
    "match_tier",
    "matching_features",
    "provenance",
]

TRIP_COLUMNS = [
    "diagnostic_variant",
    "person_day_id",
    "trip_intent_id",
    "generated_person_id",
    "generated_household_id",
    "generated_home_zone_id",
    "trip_sequence_index",
    "canonical_trip_purpose",
    "origin_activity",
    "destination_activity",
    "destination_resolution",
    "departure_clock_minute",
    "arrival_clock_minute",
    "arrival_day_offset",
    "duration_from_clock_min",
    "distance_prior_km",
    "distance_prior_provenance",
    "source_distance_status",
    "temporal_row_status",
    "spatial_realization_status",
    "mode_status",
    "diary_source_hp_id",
    "provenance",
]

DONOR_POOL_COLUMNS = [
    "HP_ID",
    "H_ID_num",
    "P_ID",
    "age_infr_class",
    "sex",
    "primary_activity_status",
    "employment_participation",
    "household_size_class",
    "mobil_diff",
    "analytic_total_trip_count",
    "replay_complete_zero",
    "replay_complete_mobile",
    "P_GEW",
]

RAW_PERSON_COLUMNS = [
    "HP_ID",
    "H_ID",
    "P_ID",
    "P_GEW",
    "ST_MONAT",
    "ST_JAHR",
    "ST_WOTAG",
    "ST_WOCHE",
    "feiertag",
    "saison",
    "mobil_diff",
    "HP_SEX",
    "HP_ALTER",
    "HP_TAET",
    "H_GR",
]


def _bool_value(value: Any) -> bool:
    if pd.isna(value):
        return False
    if isinstance(value, (bool, np.bool_)):
        return bool(value)
    return str(value).strip().lower() in {"true", "1", "yes"}


def load_raw_persons(path: Path) -> pd.DataFrame:
    """Load only MiD Personen fields required by the frozen replay bridge."""
    frame = pd.read_csv(path, usecols=RAW_PERSON_COLUMNS, low_memory=False)
    frame["HP_ID"] = pd.to_numeric(frame["HP_ID"], errors="raise").astype("int64")
    frame["H_ID"] = pd.to_numeric(frame["H_ID"], errors="raise").astype("int64")
    frame["P_ID"] = pd.to_numeric(frame["P_ID"], errors="raise").astype("int64")
    return frame


def load_replay_evidence(
    *,
    coverage_path: Path,
    functional_path: Path,
    temporal_sequence_path: Path,
    transition_path: Path,
    trip_time_path: Path,
    spatial_path: Path,
) -> dict[str, pd.DataFrame]:
    """Load frozen F0.3 evidence tables without reinterpreting source semantics."""
    coverage = pd.read_csv(coverage_path, low_memory=False)
    functional = pd.read_csv(functional_path, low_memory=False)
    temporal_sequence = pd.read_csv(temporal_sequence_path, low_memory=False)
    transition = pd.read_csv(transition_path, low_memory=False)
    trip_time = pd.read_csv(trip_time_path, low_memory=False)
    spatial = pd.read_csv(spatial_path, low_memory=False)

    for frame in (coverage, functional, temporal_sequence, transition, trip_time, spatial):
        frame["HP_ID"] = pd.to_numeric(frame["HP_ID"], errors="coerce").astype("Int64")
    for frame in (transition, trip_time, spatial):
        frame["W_ID"] = pd.to_numeric(frame["W_ID"], errors="coerce").astype("Int64")

    return {
        "coverage": coverage,
        "functional": functional,
        "temporal_sequence": temporal_sequence,
        "transition": transition,
        "trip_time": trip_time,
        "spatial": spatial,
    }


def _source_indexes(
    raw_persons: pd.DataFrame,
    evidence: dict[str, pd.DataFrame],
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    raw = raw_persons.set_index("HP_ID", drop=False)
    coverage = evidence["coverage"].set_index("HP_ID", drop=False)
    functional = evidence["functional"].set_index("HP_ID", drop=False)
    temporal = evidence["temporal_sequence"].set_index("HP_ID", drop=False)
    return raw, coverage, functional, temporal


def build_replay_persondays(
    population_persons: pd.DataFrame,
    raw_persons: pd.DataFrame,
    evidence: dict[str, pd.DataFrame],
) -> pd.DataFrame:
    """Materialize one D_REPLAY person-day row per generated M-scale person."""
    raw, coverage, functional, temporal = _source_indexes(raw_persons, evidence)
    rows: list[dict[str, Any]] = []

    for person in population_persons.itertuples(index=False):
        source_id = person.source_person_id
        row: dict[str, Any] = {
            "diagnostic_variant": "D_REPLAY_EXACT_V1",
            "person_day_id": f"PD_D_REPLAY_EXACT_V1_{person.person_id}",
            "generated_person_id": person.person_id,
            "generated_household_id": person.household_id,
            "generated_home_zone_id": person.home_zone_id,
        }

        if pd.isna(source_id):
            row.update(
                {
                    "diary_source_hp_id": np.nan,
                    "diary_source_household_id": pd.NA,
                    "diary_source_split": np.nan,
                    "assignment_status": "UNAVAILABLE_NO_PERSONDAY",
                    "plan_status": "INCOMPLETE",
                    "day_mobility_status": np.nan,
                    "participation_class": np.nan,
                    "analytic_total_trip_count": np.nan,
                    "chain_coverage_status": np.nan,
                    "full_functional_day_sequence_eligible": np.nan,
                    "temporal_sequence_fit_eligible": np.nan,
                    "survey_year": np.nan,
                    "survey_month": np.nan,
                    "survey_calendar_week": np.nan,
                    "survey_weekday": np.nan,
                    "source_holiday": np.nan,
                    "source_season": np.nan,
                    "diary_person_weight": np.nan,
                    "match_tier": "EXACT_SOURCE_PERSON",
                    "matching_features": "NONE_REQUIRED",
                    "provenance": "EXACT_SOURCE_PERSON_DAY_REPLAY",
                }
            )
            rows.append(row)
            continue

        hp_id = int(source_id)
        source = raw.loc[hp_id]
        cov = coverage.loc[hp_id]
        functional_ok = (
            _bool_value(functional.loc[hp_id, "full_functional_day_sequence_eligible"])
            if hp_id in functional.index
            else False
        )
        temporal_ok = (
            _bool_value(temporal.loc[hp_id, "temporal_sequence_fit_eligible"])
            if hp_id in temporal.index
            else False
        )
        mobility_code = int(source["mobil_diff"])
        day_status, participation_class = DAY_STATUS[mobility_code]

        if mobility_code == 0:
            assignment = "COMPLETE_ZERO_TRIP"
        elif mobility_code == 4:
            assignment = "OUT_OF_SCOPE_FAR_ABROAD"
        elif mobility_code == 5:
            assignment = "PARTIAL_PARTICIPATION_ONLY"
        elif mobility_code == 6:
            assignment = "SENSITIVITY_NONMOBILE_REPORTING_RISK"
        elif mobility_code == 9:
            assignment = "UNKNOWN_MOBILITY"
        elif (
            cov["chain_coverage_status"] == "DIRECT_REPORTED_CHAIN_COMPLETE"
            and functional_ok
            and temporal_ok
        ):
            assignment = "COMPLETE_MOBILE_DAY"
        else:
            assignment = "PARTIAL_COUNT_OR_CHAIN_ONLY"

        plan_status = (
            assignment
            if assignment in {"COMPLETE_ZERO_TRIP", "COMPLETE_MOBILE_DAY"}
            else "INCOMPLETE"
        )
        row.update(
            {
                "diary_source_hp_id": float(hp_id),
                "diary_source_household_id": int(source["H_ID"]),
                "diary_source_split": "TRAIN",
                "assignment_status": assignment,
                "plan_status": plan_status,
                "day_mobility_status": day_status,
                "participation_class": participation_class,
                "analytic_total_trip_count": cov["analytic_total_trip_count"],
                "chain_coverage_status": cov["chain_coverage_status"],
                "full_functional_day_sequence_eligible": functional_ok,
                "temporal_sequence_fit_eligible": temporal_ok,
                "survey_year": float(source["ST_JAHR"]),
                "survey_month": float(source["ST_MONAT"]),
                "survey_calendar_week": float(source["ST_WOCHE"]),
                "survey_weekday": float(source["ST_WOTAG"]),
                "source_holiday": float(source["feiertag"]),
                "source_season": float(source["saison"]),
                "diary_person_weight": source["P_GEW"],
                "match_tier": "EXACT_SOURCE_PERSON",
                "matching_features": "SOURCE_PERSON_ID_ONLY",
                "provenance": "EXACT_SOURCE_PERSON_DAY_REPLAY",
            }
        )
        rows.append(row)

    result = pd.DataFrame(rows, columns=PERSONDAY_COLUMNS)
    # Historical serialization used nullable integer household lineage but float HP_ID.
    result["diary_source_household_id"] = pd.array(
        result["diary_source_household_id"], dtype="Int64"
    )
    return result


def build_replay_trips(
    replay_persondays: pd.DataFrame,
    evidence: dict[str, pd.DataFrame],
) -> pd.DataFrame:
    """Materialize TripIntent diagnostics for complete mobile replay days only."""
    mobile = replay_persondays[
        replay_persondays["assignment_status"] == "COMPLETE_MOBILE_DAY"
    ].copy()
    mobile["HP_ID"] = mobile["diary_source_hp_id"].astype("int64")
    mobile["_generated_order"] = np.arange(len(mobile), dtype=np.int64)

    transition = evidence["transition"]
    trip_time = evidence["trip_time"]
    spatial = evidence["spatial"]
    transition = transition[
        pd.to_numeric(transition["W_RBW"], errors="coerce").fillna(-1).astype(int) == 0
    ]
    trip_time = trip_time[
        pd.to_numeric(trip_time["W_RBW"], errors="coerce").fillna(-1).astype(int) == 0
    ]
    spatial = spatial[
        pd.to_numeric(spatial["W_RBW"], errors="coerce").fillna(-1).astype(int) == 0
    ]

    source = transition[
        [
            "HP_ID",
            "W_ID",
            "canonical_trip_purpose",
            "origin_activity",
            "destination_activity",
            "destination_resolution",
        ]
    ].merge(
        trip_time[
            [
                "HP_ID",
                "W_ID",
                "departure_clock_minute",
                "arrival_clock_minute",
                "arrival_day_offset",
                "duration_from_clock_min",
                "temporal_row_status",
            ]
        ],
        on=["HP_ID", "W_ID"],
        validate="one_to_one",
    ).merge(
        spatial[
            ["HP_ID", "W_ID", "wegkm", "wegkm_imp", "source_distance_status"]
        ],
        on=["HP_ID", "W_ID"],
        validate="one_to_one",
    )

    result = mobile.merge(source, on="HP_ID", how="left", sort=False, validate="many_to_many")
    result = result.sort_values(["_generated_order", "W_ID"], kind="stable").reset_index(drop=True)
    result["trip_sequence_index"] = result.groupby("_generated_order", sort=False).cumcount() + 1
    result["distance_prior_km"] = np.where(
        result["source_distance_status"].eq("DIRECT_SOURCE_DISTANCE_VALID"),
        result["wegkm"],
        result["wegkm_imp"],
    )
    result["distance_prior_provenance"] = np.where(
        result["source_distance_status"].eq("DIRECT_SOURCE_DISTANCE_VALID"),
        "OBSERVED_SOURCE_PATH_LENGTH",
        "SOURCE_IMPUTED_PATH_LENGTH_DIAGNOSTIC",
    )
    result["diagnostic_variant"] = "D_REPLAY_EXACT_V1"
    result["trip_intent_id"] = (
        result["person_day_id"]
        + "_T"
        + result["trip_sequence_index"].astype(str).str.zfill(2)
    )
    result["spatial_realization_status"] = "NOT_REALIZED_M2_ONLY"
    result["mode_status"] = "NOT_AVAILABLE_M2"
    result["provenance"] = "SOURCE_DIARY_REPLAY_M2_DIAGNOSTIC"
    result["diary_source_hp_id"] = result["HP_ID"].astype("int64")

    result = result.loc[:, TRIP_COLUMNS]
    for column in ("generated_home_zone_id", "trip_sequence_index", "diary_source_hp_id"):
        result[column] = result[column].astype("int64")
    return result


def strict_train_source_persons(
    split_manifest: pd.DataFrame,
    raw_persons: pd.DataFrame,
) -> pd.DataFrame:
    """Return the frozen strict-TRAIN source person-day universe in source order."""
    strict = split_manifest[
        (split_manifest["split"] == "TRAIN")
        & split_manifest["joint_rmin_donor_eligible"].astype(bool)
    ]
    household_ids = set(strict["source_household_id"].astype(int).tolist())
    return raw_persons[raw_persons["H_ID"].astype(int).isin(household_ids)].copy()


def build_full_day_donor_pool(
    split_manifest: pd.DataFrame,
    raw_persons: pd.DataFrame,
    evidence: dict[str, pd.DataFrame],
    activity_recoding_path: Path,
) -> pd.DataFrame:
    """Recreate the exact historical complete diary donor pool used later by D_MATCH."""
    source = strict_train_source_persons(split_manifest, raw_persons)
    _, coverage, functional, temporal = _source_indexes(raw_persons, evidence)
    activity = load_activity_recoding(activity_recoding_path)
    rows: list[dict[str, Any]] = []

    for person in source.itertuples(index=False):
        hp_id = int(person.HP_ID)
        mobility_code = int(person.mobil_diff)
        replay_zero = mobility_code == 0
        replay_mobile = (
            mobility_code in {1, 2, 3}
            and coverage.loc[hp_id, "chain_coverage_status"]
            == "DIRECT_REPORTED_CHAIN_COMPLETE"
            and _bool_value(functional.loc[hp_id, "full_functional_day_sequence_eligible"])
            and _bool_value(temporal.loc[hp_id, "temporal_sequence_fit_eligible"])
        )
        if not (replay_zero or replay_mobile):
            continue
        primary_activity, employment_participation, _ = activity[int(person.HP_TAET)]
        rows.append(
            {
                "HP_ID": hp_id,
                "H_ID_num": int(person.H_ID),
                "P_ID": int(person.P_ID),
                "age_infr_class": age_infr_class(int(person.HP_ALTER)),
                "sex": {1: "MALE", 2: "FEMALE"}.get(int(person.HP_SEX), "UNKNOWN"),
                "primary_activity_status": primary_activity,
                "employment_participation": employment_participation,
                "household_size_class": int(person.H_GR),
                "mobil_diff": mobility_code,
                "analytic_total_trip_count": coverage.loc[
                    hp_id, "analytic_total_trip_count"
                ],
                "replay_complete_zero": replay_zero,
                "replay_complete_mobile": replay_mobile,
                "P_GEW": person.P_GEW,
            }
        )
    return pd.DataFrame(rows, columns=DONOR_POOL_COLUMNS)


def replay_assignment_summary(replay_persondays: pd.DataFrame) -> pd.DataFrame:
    counts = replay_persondays["assignment_status"].value_counts()
    order = [
        "COMPLETE_MOBILE_DAY",
        "PARTIAL_COUNT_OR_CHAIN_ONLY",
        "UNAVAILABLE_NO_PERSONDAY",
        "COMPLETE_ZERO_TRIP",
        "PARTIAL_PARTICIPATION_ONLY",
        "OUT_OF_SCOPE_FAR_ABROAD",
        "UNKNOWN_MOBILITY",
        "SENSITIVITY_NONMOBILE_REPORTING_RISK",
    ]
    total = len(replay_persondays)
    return pd.DataFrame(
        {
            "assignment_status": order,
            "n": [int(counts.get(status, 0)) for status in order],
            "share": [float(counts.get(status, 0)) / total for status in order],
        }
    )


def validate_replay(
    *,
    population_persons: pd.DataFrame,
    replay_persondays: pd.DataFrame,
    replay_trips: pd.DataFrame,
    source_persons: pd.DataFrame,
    full_day_pool: pd.DataFrame,
    expected_assignment: dict[str, int],
    expected_complete: int,
    expected_trips: int,
) -> pd.DataFrame:
    """Replay-only structural checks; R6 will execute the combined F2.1 suite."""
    checks: list[tuple[str, str, str, bool, str]] = []

    def add(check_id: str, category: str, description: str, ok: bool, details: str = "") -> None:
        checks.append((check_id, category, description, bool(ok), details))

    add("R5-001", "TARGET", "One replay row per generated person", len(replay_persondays) == len(population_persons), f"person_days={len(replay_persondays)}")
    add("R5-002", "PK", "Replay person_day_id unique", replay_persondays["person_day_id"].is_unique)
    add("R5-003", "IDENTITY", "Replay generated_person_id unique", replay_persondays["generated_person_id"].is_unique)
    add("R5-004", "FK", "Replay covers exactly the R4 generated person IDs", set(replay_persondays["generated_person_id"]) == set(population_persons["person_id"]))
    linked = replay_persondays[replay_persondays["diary_source_hp_id"].notna()]
    unavailable = replay_persondays[replay_persondays["diary_source_hp_id"].isna()]
    add("R5-005", "REPLAY", "Linked replay uses exact generated source person only", (linked["diary_source_hp_id"].astype("int64").to_numpy() == population_persons.loc[population_persons["source_person_id"].notna(), "source_person_id"].astype("int64").to_numpy()).all())
    add("R5-006", "REPLAY", "No donor substitution for roster-only persons", unavailable["assignment_status"].eq("UNAVAILABLE_NO_PERSONDAY").all(), f"unavailable={len(unavailable)}")
    strict_train_hp = set(source_persons["HP_ID"].astype("int64"))
    linked_hp = set(linked["diary_source_hp_id"].astype("int64"))
    add(
        "R5-007",
        "SPLIT",
        "All available replay source diaries resolve to strict TRAIN source persons",
        linked["diary_source_split"].eq("TRAIN").all()
        and linked_hp.issubset(strict_train_hp),
    )
    actual_assignment = replay_persondays["assignment_status"].value_counts().to_dict()
    add("R5-008", "COVERAGE", "Assignment-status counts match frozen F2.1 replay", all(int(actual_assignment.get(k, 0)) == int(v) for k, v in expected_assignment.items()), str({k: int(actual_assignment.get(k, 0)) for k in expected_assignment}))
    complete = int(replay_persondays["plan_status"].isin(["COMPLETE_ZERO_TRIP", "COMPLETE_MOBILE_DAY"]).sum())
    add("R5-009", "COVERAGE", "Complete replay person-days match frozen anchor", complete == expected_complete, f"complete={complete}")
    add("R5-010", "TRIPS", "Replay trip-intent count matches frozen anchor", len(replay_trips) == expected_trips, f"trips={len(replay_trips)}")
    mobile_ids = set(replay_persondays.loc[replay_persondays["assignment_status"] == "COMPLETE_MOBILE_DAY", "person_day_id"])
    add("R5-011", "TRIPS", "Trip intents exist only for complete mobile replay days", set(replay_trips["person_day_id"]).issubset(mobile_ids))
    trip_counts = replay_trips.groupby("person_day_id").size()
    expected_counts = replay_persondays.loc[replay_persondays["assignment_status"] == "COMPLETE_MOBILE_DAY", ["person_day_id", "analytic_total_trip_count"]].set_index("person_day_id")["analytic_total_trip_count"].astype(int)
    add("R5-012", "COUNT", "Complete mobile TripIntent rows equal analytic_total_trip_count", trip_counts.equals(expected_counts))
    zero_ids = set(replay_persondays.loc[replay_persondays["assignment_status"] == "COMPLETE_ZERO_TRIP", "person_day_id"])
    add("R5-013", "SEMANTIC", "Complete zero-trip days emit no TripIntent", not bool(zero_ids.intersection(set(replay_trips["person_day_id"]))))
    add("R5-014", "TEMPORAL", "Replay TripIntent rows are direct temporal-valid observations", replay_trips["temporal_row_status"].eq("DIRECT_TEMPORAL_VALID").all())
    add("R5-015", "NFI", "M2 replay output excludes observed/chosen mode and execution outcomes", replay_trips["mode_status"].eq("NOT_AVAILABLE_M2").all() and replay_trips["spatial_realization_status"].eq("NOT_REALIZED_M2_ONLY").all())
    add("R5-016", "SOURCE_POOL", "Strict TRAIN source person-day pool has 2,200 rows", len(source_persons) == 2200, f"source_person_days={len(source_persons)}")
    add("R5-017", "SOURCE_POOL", "Full-day donor pool has 1,658 rows", len(full_day_pool) == 1658, f"full_day={len(full_day_pool)}")
    add("R5-018", "SOURCE_POOL", "Full-day pool split is 261 zero-trip + 1,397 mobile", int(full_day_pool["replay_complete_zero"].sum()) == 261 and int(full_day_pool["replay_complete_mobile"].sum()) == 1397)

    return pd.DataFrame(
        [
            {
                "check_id": check_id,
                "category": category,
                "description": description,
                "result": "PASS" if ok else "FAIL",
                "details": details,
            }
            for check_id, category, description, ok, details in checks
        ]
    )
