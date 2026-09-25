"""Deterministic reconstruction of the frozen F2.1 D_MATCH diagnostic lane."""

from __future__ import annotations

import hashlib
from collections import defaultdict
from typing import Any

import numpy as np
import pandas as pd

from simfleet_edg.common.demand_replay import DAY_STATUS, TRIP_COLUMNS

MATCH_VARIANT_ID = "D_MATCH_FULLDAY_V1"

MATCH_PERSONDAY_COLUMNS = [
    "diagnostic_variant",
    "person_day_id",
    "generated_person_id",
    "generated_household_id",
    "generated_home_zone_id",
    "generated_age_infr_class",
    "generated_sex",
    "generated_primary_activity_status",
    "generated_employment_participation",
    "generated_household_size_class",
    "generated_source_hp_id",
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
    "donor_age_infr_class",
    "donor_sex",
    "donor_primary_activity_status",
    "donor_employment_participation",
    "donor_household_size_class",
    "match_tier",
    "matching_features",
    "relaxed_due_to_self_only",
    "self_diary_match",
    "provenance",
]

MATCH_TIERS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "T1_EXACT_AGE_SEX_ACTIVITY_HHSIZE",
        ("age_infr_class", "sex", "primary_activity_status", "household_size_class"),
    ),
    (
        "T2_RELAX_HHSIZE",
        ("age_infr_class", "sex", "primary_activity_status"),
    ),
    (
        "T3_RELAX_ACTIVITY_TO_EMPLOYMENT",
        ("age_infr_class", "sex", "employment_participation"),
    ),
    ("T4_AGE_SEX", ("age_infr_class", "sex")),
    ("T5_AGE_ONLY", ("age_infr_class",)),
)

ALLOWED_MATCH_FEATURES = {
    "age_infr_class",
    "sex",
    "primary_activity_status",
    "employment_participation",
    "household_size_class",
}

FORBIDDEN_MATCH_FEATURES = {
    "participation_outcome",
    "trip_count",
    "purpose",
    "departure_time",
    "arrival_time",
    "distance",
    "observed_mode",
    "chosen_mode",
    "execution_outcome",
}


def _bool_value(value: Any) -> bool:
    if pd.isna(value):
        return False
    if isinstance(value, (bool, np.bool_)):
        return bool(value)
    return str(value).strip().lower() in {"true", "1", "yes"}


def _generated_population(
    persons: pd.DataFrame,
    households: pd.DataFrame,
) -> pd.DataFrame:
    """Attach frozen household-size state required by the historical matching tiers."""
    required_person = {
        "person_id",
        "household_id",
        "home_zone_id",
        "source_person_id",
        "age_infr_class",
        "sex",
        "primary_activity_status",
        "employment_participation",
    }
    required_household = {"household_id", "materialized_member_count"}
    missing_person = required_person.difference(persons.columns)
    missing_household = required_household.difference(households.columns)
    if missing_person:
        raise ValueError(f"R4 persons missing columns: {sorted(missing_person)}")
    if missing_household:
        raise ValueError(f"R4 households missing columns: {sorted(missing_household)}")

    generated = persons.merge(
        households[["household_id", "materialized_member_count"]],
        on="household_id",
        how="left",
        validate="many_to_one",
    )
    if generated["materialized_member_count"].isna().any():
        raise ValueError("Generated person without materialized household size")
    generated["household_size_class"] = (
        generated["materialized_member_count"].astype(int).astype(str)
    )
    return generated


def _source_indexes(
    raw_persons: pd.DataFrame,
    evidence: dict[str, pd.DataFrame],
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    raw = raw_persons.set_index("HP_ID", drop=False)
    coverage = evidence["coverage"].set_index("HP_ID", drop=False)
    functional = evidence["functional"].set_index("HP_ID", drop=False)
    temporal = evidence["temporal_sequence"].set_index("HP_ID", drop=False)
    return raw, coverage, functional, temporal


def _tier_pools(
    donor_pool: pd.DataFrame,
) -> list[tuple[str, tuple[str, ...], dict[tuple[str, ...], list[int]]]]:
    pools: list[tuple[str, tuple[str, ...], dict[tuple[str, ...], list[int]]]] = []
    for tier_name, columns in MATCH_TIERS:
        mapping: dict[tuple[str, ...], list[int]] = defaultdict(list)
        for index, row in donor_pool.loc[:, list(columns)].astype(str).iterrows():
            mapping[tuple(row.values.tolist())].append(int(index))
        pools.append((tier_name, columns, mapping))
    return pools


def build_match_persondays(
    *,
    population_persons: pd.DataFrame,
    population_households: pd.DataFrame,
    donor_pool: pd.DataFrame,
    raw_persons: pd.DataFrame,
    evidence: dict[str, pd.DataFrame],
    seed: int,
) -> pd.DataFrame:
    """Match every generated person to another complete strict-TRAIN source diary."""
    donors = donor_pool.reset_index(drop=True).copy()
    if donors.empty:
        raise ValueError("D_MATCH donor pool is empty")
    complete = donors["replay_complete_zero"].map(_bool_value) | donors[
        "replay_complete_mobile"
    ].map(_bool_value)
    if not complete.all():
        raise ValueError("D_MATCH donor pool contains an incomplete diary")

    generated = _generated_population(population_persons, population_households)
    raw, coverage, functional, temporal = _source_indexes(raw_persons, evidence)
    pools = _tier_pools(donors)
    rng = np.random.default_rng(seed)
    rows: list[dict[str, Any]] = []

    for person in generated.itertuples(index=False):
        values = person._asdict()
        source_hp = values.get("source_person_id")
        chosen_index: int | None = None
        chosen_tier: str | None = None
        chosen_features: str | None = None
        relaxed_due_to_self_only = False

        for tier_name, columns, pool in pools:
            key = tuple(str(values[column]) for column in columns)
            candidates = pool.get(key)
            if not candidates:
                continue
            candidate_index = np.asarray(candidates, dtype=np.int64)
            if pd.notna(source_hp):
                not_self = (
                    donors.loc[candidate_index, "HP_ID"].astype(int).to_numpy()
                    != int(source_hp)
                )
            else:
                not_self = np.ones(len(candidate_index), dtype=bool)
            if int(not_self.sum()) == 0:
                relaxed_due_to_self_only = True
                continue
            candidate_index = candidate_index[not_self]
            weights = donors.loc[candidate_index, "P_GEW"].astype(float).to_numpy()
            weights = weights / weights.sum()
            chosen_index = int(rng.choice(candidate_index, p=weights))
            chosen_tier = tier_name
            chosen_features = ";".join(columns)
            break

        if chosen_index is None:
            candidate_index = np.arange(len(donors), dtype=np.int64)
            if pd.notna(source_hp):
                candidate_index = candidate_index[
                    donors.loc[candidate_index, "HP_ID"].astype(int).to_numpy()
                    != int(source_hp)
                ]
            if len(candidate_index) == 0:
                raise ValueError("No non-self diary available for global fallback")
            weights = donors.loc[candidate_index, "P_GEW"].astype(float).to_numpy()
            weights = weights / weights.sum()
            chosen_index = int(rng.choice(candidate_index, p=weights))
            chosen_tier = "T6_GLOBAL_FALLBACK"
            chosen_features = "NONE"

        donor = donors.iloc[chosen_index]
        hp_id = int(donor["HP_ID"])
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
        mobility_code = int(donor["mobil_diff"])
        day_status, participation_class = DAY_STATUS[mobility_code]
        replay_zero = _bool_value(donor["replay_complete_zero"])
        replay_mobile = _bool_value(donor["replay_complete_mobile"])
        if replay_zero == replay_mobile:
            raise ValueError(f"Invalid complete-day donor flags for HP_ID={hp_id}")
        plan_status = "COMPLETE_ZERO_TRIP" if replay_zero else "COMPLETE_MOBILE_DAY"
        trip_count = 0 if replay_zero else int(donor["analytic_total_trip_count"])
        source_hp_value = None if pd.isna(source_hp) else int(source_hp)

        rows.append(
            {
                "diagnostic_variant": MATCH_VARIANT_ID,
                "person_day_id": f"PD_{MATCH_VARIANT_ID}_{person.person_id}",
                "generated_person_id": person.person_id,
                "generated_household_id": person.household_id,
                "generated_home_zone_id": person.home_zone_id,
                "generated_age_infr_class": person.age_infr_class,
                "generated_sex": person.sex,
                "generated_primary_activity_status": person.primary_activity_status,
                "generated_employment_participation": person.employment_participation,
                "generated_household_size_class": person.household_size_class,
                "generated_source_hp_id": source_hp_value,
                "diary_source_hp_id": hp_id,
                "diary_source_household_id": int(donor["H_ID_num"]),
                "diary_source_split": "TRAIN",
                "assignment_status": "MATCHED_COMPLETE_DIARY",
                "plan_status": plan_status,
                "day_mobility_status": day_status,
                "participation_class": participation_class,
                "analytic_total_trip_count": trip_count,
                "chain_coverage_status": cov["chain_coverage_status"],
                "full_functional_day_sequence_eligible": functional_ok,
                "temporal_sequence_fit_eligible": temporal_ok,
                "survey_year": int(source["ST_JAHR"]),
                "survey_month": int(source["ST_MONAT"]),
                "survey_calendar_week": int(source["ST_WOCHE"]),
                "survey_weekday": int(source["ST_WOTAG"]),
                "source_holiday": int(source["feiertag"]),
                "source_season": source["saison"],
                "diary_person_weight": float(donor["P_GEW"]),
                "donor_age_infr_class": donor["age_infr_class"],
                "donor_sex": donor["sex"],
                "donor_primary_activity_status": donor["primary_activity_status"],
                "donor_employment_participation": donor["employment_participation"],
                "donor_household_size_class": donor["household_size_class"],
                "match_tier": chosen_tier,
                "matching_features": chosen_features,
                "relaxed_due_to_self_only": relaxed_due_to_self_only,
                "self_diary_match": False,
                "provenance": "STATIC_ATTRIBUTE_WEIGHTED_DIARY_MATCH",
            }
        )

    return pd.DataFrame(rows, columns=MATCH_PERSONDAY_COLUMNS)


def build_match_trips(
    match_persondays: pd.DataFrame,
    evidence: dict[str, pd.DataFrame],
) -> pd.DataFrame:
    """Materialize historical M2 TripIntent rows for matched complete mobile diaries."""
    transition = evidence["transition"].copy()
    trip_time = evidence["trip_time"].copy()
    spatial = evidence["spatial"].copy()
    for frame in (transition, trip_time, spatial):
        frame = frame
    transition = transition[
        pd.to_numeric(transition["W_RBW"], errors="coerce").fillna(-1).astype(int) == 0
    ]
    trip_time = trip_time[
        pd.to_numeric(trip_time["W_RBW"], errors="coerce").fillna(-1).astype(int) == 0
    ]
    spatial = spatial[
        pd.to_numeric(spatial["W_RBW"], errors="coerce").fillna(-1).astype(int) == 0
    ]

    template = transition[
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

    mobile = match_persondays[
        match_persondays["plan_status"] == "COMPLETE_MOBILE_DAY"
    ].copy()
    mobile["HP_ID"] = mobile["diary_source_hp_id"].astype("int64")
    result = mobile[
        [
            "person_day_id",
            "generated_person_id",
            "generated_household_id",
            "generated_home_zone_id",
            "diary_source_hp_id",
            "HP_ID",
        ]
    ].merge(template, on="HP_ID", how="left", sort=False, validate="many_to_many")
    result = result[result["W_ID"].notna()].copy()

    raw_distance = pd.to_numeric(result["wegkm"], errors="coerce")
    imputed_distance = pd.to_numeric(result["wegkm_imp"], errors="coerce")
    raw_valid = raw_distance.between(0.01, 950)
    imputed_valid = imputed_distance.between(0.01, 950)
    result["distance_prior_km"] = np.where(raw_valid, raw_distance, imputed_distance)
    result["distance_prior_provenance"] = np.where(
        raw_valid,
        "OBSERVED_SOURCE_PATH_LENGTH",
        np.where(
            imputed_valid,
            "SOURCE_IMPUTED_PATH_LENGTH_DIAGNOSTIC",
            "DISTANCE_PRIOR_UNAVAILABLE",
        ),
    )
    result["diagnostic_variant"] = MATCH_VARIANT_ID
    result["trip_sequence_index"] = result["W_ID"].astype(int)
    result["trip_intent_id"] = (
        result["person_day_id"]
        + "_T"
        + result["trip_sequence_index"].astype(str).str.zfill(2)
    )
    result["spatial_realization_status"] = "NOT_REALIZED_M2_ONLY"
    result["mode_status"] = "NOT_AVAILABLE_M2"
    result["provenance"] = "MATCHED_SOURCE_DIARY_M2_DIAGNOSTIC"

    result = result.loc[:, TRIP_COLUMNS]
    return result.sort_values(
        ["generated_person_id", "trip_sequence_index"], kind="stable"
    ).reset_index(drop=True)


def match_tier_summary(match_persondays: pd.DataFrame) -> pd.DataFrame:
    order = [tier for tier, _ in MATCH_TIERS] + ["T6_GLOBAL_FALLBACK"]
    counts = match_persondays["match_tier"].value_counts()
    total = len(match_persondays)
    return pd.DataFrame(
        {
            "match_tier": order,
            "n": [int(counts.get(tier, 0)) for tier in order],
            "share": [float(counts.get(tier, 0)) / total for tier in order],
        }
    )


def diary_donor_reuse(
    replay_persondays: pd.DataFrame,
    match_persondays: pd.DataFrame,
) -> pd.DataFrame:
    replay = (
        replay_persondays.dropna(subset=["diary_source_hp_id"])
        .groupby("diary_source_hp_id")
        .size()
        .rename("n_assignments")
        .reset_index()
    )
    replay["diagnostic_variant"] = "D_REPLAY_EXACT_V1"
    match = (
        match_persondays.groupby("diary_source_hp_id")
        .size()
        .rename("n_assignments")
        .reset_index()
    )
    match["diagnostic_variant"] = MATCH_VARIANT_ID
    return pd.concat([replay, match], ignore_index=True)


def bridge_summary(
    replay_persondays: pd.DataFrame,
    replay_trips: pd.DataFrame,
    match_persondays: pd.DataFrame,
    match_trips: pd.DataFrame,
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    replay_counts = replay_persondays["assignment_status"].value_counts()
    for status, count in replay_counts.items():
        rows.append(
            {
                "dimension": "D_REPLAY_assignment_status",
                "category": status,
                "n": int(count),
                "share": float(count) / len(replay_persondays),
                "notes": "",
            }
        )
    tier_counts = match_persondays["match_tier"].value_counts()
    for tier, count in tier_counts.items():
        rows.append(
            {
                "dimension": "D_MATCH_match_tier",
                "category": tier,
                "n": int(count),
                "share": float(count) / len(match_persondays),
                "notes": "",
            }
        )
    for variant, persondays, trips in (
        ("D_REPLAY_EXACT_V1", replay_persondays, replay_trips),
        (MATCH_VARIANT_ID, match_persondays, match_trips),
    ):
        for status in ("COMPLETE_ZERO_TRIP", "COMPLETE_MOBILE_DAY", "INCOMPLETE"):
            count = int(persondays["plan_status"].eq(status).sum())
            rows.append(
                {
                    "dimension": "plan_coverage",
                    "category": f"{variant}:{status}",
                    "n": count,
                    "share": count / len(persondays),
                    "notes": "",
                }
            )
        rows.append(
            {
                "dimension": "trip_output",
                "category": variant,
                "n": len(trips),
                "share": np.nan,
                "notes": "materialized M2 diagnostic trip intents",
            }
        )
    pairs = (
        ("AGE_EXACT", "generated_age_infr_class", "donor_age_infr_class"),
        ("SEX_EXACT", "generated_sex", "donor_sex"),
        (
            "ACTIVITY_EXACT",
            "generated_primary_activity_status",
            "donor_primary_activity_status",
        ),
        (
            "EMPLOYMENT_EXACT",
            "generated_employment_participation",
            "donor_employment_participation",
        ),
        (
            "HOUSEHOLD_SIZE_EXACT",
            "generated_household_size_class",
            "donor_household_size_class",
        ),
    )
    for label, generated_column, donor_column in pairs:
        exact = match_persondays[generated_column].astype(str).eq(
            match_persondays[donor_column].astype(str)
        )
        rows.append(
            {
                "dimension": "D_MATCH_static_alignment",
                "category": label,
                "n": int(exact.sum()),
                "share": float(exact.mean()),
                "notes": "",
            }
        )
    return pd.DataFrame(rows)


def distance_prior_audit(
    replay_trips: pd.DataFrame,
    match_trips: pd.DataFrame,
) -> pd.DataFrame:
    frame = pd.concat(
        [
            replay_trips.assign(_variant="D_REPLAY_EXACT_V1"),
            match_trips.assign(_variant=MATCH_VARIANT_ID),
        ],
        ignore_index=True,
    )
    result = (
        frame.groupby(["_variant", "distance_prior_provenance"])
        .size()
        .reset_index(name="n")
    )
    result["share_within_variant"] = result.groupby("_variant")["n"].transform(
        lambda values: values / values.sum()
    )
    return result


def combined_bridge_sha256(
    replay_persondays_sha256: str,
    match_persondays_sha256: str,
    replay_trips_sha256: str,
    match_trips_sha256: str,
) -> str:
    payload = (
        replay_persondays_sha256
        + match_persondays_sha256
        + replay_trips_sha256
        + match_trips_sha256
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def validate_match(
    *,
    match_persondays: pd.DataFrame,
    match_trips: pd.DataFrame,
    donor_pool: pd.DataFrame,
    split_manifest: pd.DataFrame,
    expected_tiers: dict[str, int],
    expected_trips: int,
) -> pd.DataFrame:
    checks: list[tuple[str, str, str, bool, str]] = []

    def add(check_id: str, category: str, description: str, ok: bool, details: str = "") -> None:
        checks.append((check_id, category, description, bool(ok), details))

    strict_train = split_manifest[
        (split_manifest["split"] == "TRAIN")
        & split_manifest["joint_rmin_donor_eligible"].astype(bool)
    ]
    strict_hh = set(strict_train["source_household_id"].astype(int))
    tier_counts = match_persondays["match_tier"].value_counts().to_dict()
    actual_self = (
        match_persondays["generated_source_hp_id"].notna()
        & match_persondays["generated_source_hp_id"].astype("Int64").eq(
            match_persondays["diary_source_hp_id"].astype("Int64")
        )
    )
    add("R6-001", "TARGET", "One matched day per generated person", len(match_persondays) == 100000)
    add("R6-002", "PK", "Matched person_day_id unique", match_persondays["person_day_id"].is_unique)
    add("R6-003", "COVERAGE", "Every D_MATCH day is complete", match_persondays["plan_status"].isin(["COMPLETE_ZERO_TRIP", "COMPLETE_MOBILE_DAY"]).all())
    add("R6-004", "SPLIT", "All matched diary households are strict TRAIN", match_persondays["diary_source_household_id"].astype(int).isin(strict_hh).all())
    add("R6-005", "SELF_MATCH", "D_MATCH never uses own source diary", not bool(actual_self.any()), f"self={int(actual_self.sum())}")
    add("R6-006", "TIERS", "Tier counts match frozen F2.1 anchors", all(int(tier_counts.get(k, 0)) == int(v) for k, v in expected_tiers.items()), str({k: int(tier_counts.get(k, 0)) for k in expected_tiers}))
    add("R6-007", "FALLBACK", "No global fallback required", int(tier_counts.get("T6_GLOBAL_FALLBACK", 0)) == 0)
    add("R6-008", "STATIC", "Age band preserved exactly", match_persondays["generated_age_infr_class"].astype(str).eq(match_persondays["donor_age_infr_class"].astype(str)).all())
    add("R6-009", "STATIC", "Sex preserved exactly", match_persondays["generated_sex"].eq(match_persondays["donor_sex"]).all())
    add("R6-010", "DONOR_POOL", "All diary_source_hp_id values belong to complete donor pool", set(match_persondays["diary_source_hp_id"].astype(int)).issubset(set(donor_pool["HP_ID"].astype(int))))
    add("R6-011", "TRIPS", "Trip-intent count matches frozen anchor", len(match_trips) == expected_trips, f"trips={len(match_trips)}")
    expected_counts = match_persondays.loc[
        match_persondays["plan_status"] == "COMPLETE_MOBILE_DAY",
        ["person_day_id", "analytic_total_trip_count"],
    ].set_index("person_day_id")["analytic_total_trip_count"].astype(int)
    actual_counts = match_trips.groupby("person_day_id").size()
    counts_ok = all(
        int(actual_counts.get(person_day_id, 0)) == int(expected_counts.loc[person_day_id])
        for person_day_id in expected_counts.index
    )
    add(
        "R6-012",
        "TRIPS",
        "Mobile matched trip rows equal analytic_total_trip_count",
        counts_ok,
    )
    zero_ids = set(match_persondays.loc[match_persondays["plan_status"] == "COMPLETE_ZERO_TRIP", "person_day_id"])
    add("R6-013", "NO_TRIP", "Matched zero-trip days emit no TripIntent", not bool(zero_ids.intersection(set(match_trips["person_day_id"]))))
    add("R6-014", "TIME", "All matched TripIntent rows are temporal-valid", match_trips["temporal_row_status"].eq("DIRECT_TEMPORAL_VALID").all())
    add("R6-015", "PURPOSE", "All matched trips have resolved functional activities", (~match_trips["origin_activity"].isin(["UNKNOWN", "NON_HOME_UNKNOWN"])).all() and (~match_trips["destination_activity"].isin(["UNKNOWN", "NON_HOME_UNKNOWN"])).all())
    add("R6-016", "DISTANCE", "All matched mobile trips have a distance prior", match_trips["distance_prior_km"].notna().all())
    add("R6-017", "ARCHITECTURE", "Spatial realization remains downstream M3", match_trips["spatial_realization_status"].eq("NOT_REALIZED_M2_ONLY").all())
    add("R6-018", "ARCHITECTURE", "Mode remains downstream M5", match_trips["mode_status"].eq("NOT_AVAILABLE_M2").all())

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


def combined_f2_1_validation(
    *,
    population_persons: pd.DataFrame,
    replay_persondays: pd.DataFrame,
    replay_trips: pd.DataFrame,
    match_persondays: pd.DataFrame,
    match_trips: pd.DataFrame,
    strict_train_households: set[int],
) -> pd.DataFrame:
    """Recreate the historical 20-check F2.1 bridge validation semantics."""
    rows: list[dict[str, Any]] = []

    def add(check_id: str, category: str, description: str, ok: bool, details: str = "") -> None:
        rows.append(
            {
                "check_id": check_id,
                "category": category,
                "description": description,
                "result": "PASS" if bool(ok) else "FAIL",
                "details": details,
            }
        )

    linked_replay = replay_persondays.dropna(subset=["diary_source_hp_id"]).merge(
        population_persons[["person_id", "source_person_id"]],
        left_on="generated_person_id",
        right_on="person_id",
        how="left",
    )
    add("F2-001", "CARDINALITY", "D_REPLAY has one bridge row per generated person", len(replay_persondays) == len(population_persons))
    add("F2-002", "SEMANTIC", "D_REPLAY never substitutes another person's diary", linked_replay["diary_source_hp_id"].astype(int).eq(linked_replay["source_person_id"].astype(int)).all())
    add("F2-003", "SPLIT", "All replay diaries with source evidence are TRAIN", replay_persondays.dropna(subset=["diary_source_hp_id"])["diary_source_split"].eq("TRAIN").all())
    add("F2-004", "QUALITY", "Complete replay mobile plans use functional + temporal complete diaries", replay_persondays.loc[replay_persondays["plan_status"].eq("COMPLETE_MOBILE_DAY"), ["full_functional_day_sequence_eligible", "temporal_sequence_fit_eligible"]].all(axis=1).all())
    add("F2-005", "CARDINALITY", "D_MATCH assigns one complete diary to every generated person", len(match_persondays) == len(population_persons) and match_persondays["plan_status"].isin(["COMPLETE_ZERO_TRIP", "COMPLETE_MOBILE_DAY"]).all())
    add("F2-006", "SPLIT", "Every D_MATCH diary donor is strict TRAIN", match_persondays["diary_source_household_id"].astype(int).isin(strict_train_households).all() and match_persondays["diary_source_split"].eq("TRAIN").all())
    actual_self = match_persondays["generated_source_hp_id"].notna() & match_persondays["generated_source_hp_id"].astype("Int64").eq(match_persondays["diary_source_hp_id"].astype("Int64"))
    add("F2-007", "SELF_MATCH", "D_MATCH never uses own source person diary", not bool(actual_self.any()))
    allowed_tiers = {tier for tier, _ in MATCH_TIERS} | {"T6_GLOBAL_FALLBACK"}
    add("F2-008", "MATCHING", "D_MATCH uses only predeclared static M1 tiers", match_persondays["match_tier"].isin(allowed_tiers).all())
    add("F2-009", "SUPPORT", "No global fallback was required", (~match_persondays["match_tier"].eq("T6_GLOBAL_FALLBACK")).all())
    add("F2-010", "STATIC_MATCH", "Every D_MATCH assignment preserves age and sex", match_persondays["generated_age_infr_class"].astype(str).eq(match_persondays["donor_age_infr_class"].astype(str)).all() and match_persondays["generated_sex"].eq(match_persondays["donor_sex"]).all())
    replay_counts = replay_trips.groupby("person_day_id").size()
    replay_expected = replay_persondays.set_index("person_day_id")["analytic_total_trip_count"]
    replay_mobile = replay_persondays.loc[replay_persondays["plan_status"].eq("COMPLETE_MOBILE_DAY"), "person_day_id"]
    add("F2-011", "TRIP_COUNT", "D_REPLAY trip rows equal analytic total for complete mobile days", all(int(replay_counts.get(pid, 0)) == int(replay_expected.loc[pid]) for pid in replay_mobile))
    match_counts = match_trips.groupby("person_day_id").size()
    match_expected = match_persondays.set_index("person_day_id")["analytic_total_trip_count"]
    match_mobile = match_persondays.loc[match_persondays["plan_status"].eq("COMPLETE_MOBILE_DAY"), "person_day_id"]
    match_zero = match_persondays.loc[match_persondays["plan_status"].eq("COMPLETE_ZERO_TRIP"), "person_day_id"]
    add("F2-012", "TRIP_COUNT", "D_MATCH trip rows equal analytic total for complete mobile days", all(int(match_counts.get(pid, 0)) == int(match_expected.loc[pid]) for pid in match_mobile))
    add("F2-013", "NO_TRIP", "D_MATCH zero-trip days have zero trip rows", all(int(match_counts.get(pid, 0)) == 0 for pid in match_zero))
    add("F2-014", "TIME", "All materialized diagnostic trips have valid temporal rows", replay_trips["temporal_row_status"].eq("DIRECT_TEMPORAL_VALID").all() and match_trips["temporal_row_status"].eq("DIRECT_TEMPORAL_VALID").all())
    add("F2-015", "PURPOSE", "All diagnostic trips have resolved functional activities", (~replay_trips["origin_activity"].isin(["UNKNOWN", "NON_HOME_UNKNOWN"])).all() and (~replay_trips["destination_activity"].isin(["UNKNOWN", "NON_HOME_UNKNOWN"])).all() and (~match_trips["origin_activity"].isin(["UNKNOWN", "NON_HOME_UNKNOWN"])).all() and (~match_trips["destination_activity"].isin(["UNKNOWN", "NON_HOME_UNKNOWN"])).all())
    add("F2-016", "DISTANCE", "All diagnostic mobile trips have a distance prior", replay_trips["distance_prior_km"].notna().all() and match_trips["distance_prior_km"].notna().all())
    forbidden = {"hvm", "hvm_diff1", "hvm_diff2", "hvm_imp", "core4_validation_projection", "chosen_mode", "reported_mode_atoms", "source_main_mode", "mode_family"}
    all_columns = set(map(str.lower, replay_persondays.columns)) | set(map(str.lower, match_persondays.columns)) | set(map(str.lower, replay_trips.columns)) | set(map(str.lower, match_trips.columns))
    add("F2-017", "NFI", "No observed/chosen mode field is present in M2 outputs", not any(column in all_columns for column in forbidden))
    add("F2-018", "NFI", "km_routing is not used as a distance prior", "km_routing" not in all_columns)
    add("F2-019", "ARCHITECTURE", "Spatial realization remains downstream", replay_trips["spatial_realization_status"].eq("NOT_REALIZED_M2_ONLY").all() and match_trips["spatial_realization_status"].eq("NOT_REALIZED_M2_ONLY").all())
    add("F2-020", "ARCHITECTURE", "Mode remains downstream of M2", replay_trips["mode_status"].eq("NOT_AVAILABLE_M2").all() and match_trips["mode_status"].eq("NOT_AVAILABLE_M2").all())
    return pd.DataFrame(rows)
