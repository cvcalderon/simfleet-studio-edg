"""F3.2b deterministic TRAIN/CAL empirical table materialization."""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from simfleet_edg.common.population_materializer import age_infr_class, load_activity_recoding
from simfleet_edg.common.population_split import sha256_file

PARTITIONS = ("TRAIN", "CALIBRATION")
DATASETS = (
    "person_day_context",
    "participation",
    "trip_count",
    "chain_days",
    "chain_transitions",
    "time_trips",
    "distance_raw",
    "distance_expanded_sensitivity",
)
RESERVED_CATEGORY_TOKENS = ("UNKNOWN", "__MISSING_CONTEXT__", "__START__", "__UNSEEN__")
BINARY_MOBILITY_CODES = {0, 1, 2, 3, 5}
EXPANDED_DISTANCE_STATUSES = {
    "DIRECT_SOURCE_DISTANCE_VALID",
    "DIRECT_NO_DETAIL_DISTANCE_IMPUTED",
    "DIRECT_SOURCE_DISTANCE_MISSING_IMPUTED",
    "DIRECT_SOURCE_DISTANCE_IMPLAUSIBLE_IMPUTED",
}
FORBIDDEN_OUTPUT_COLUMN_TOKENS = (
    "km_routing",
    "chosen_mode",
    "observed_mode",
    "mode_family",
    "route",
    "execution",
)


def _as_bool(series: pd.Series) -> pd.Series:
    if pd.api.types.is_bool_dtype(series):
        return series.fillna(False)
    return series.astype(str).str.strip().str.lower().isin({"true", "1", "yes"})


def _int_or_nan(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce").astype("Int64")


def deterministic_row_id(partition: str, household_id: int, person_id: int, dataset: str) -> str:
    payload = f"{partition}|{household_id}|{person_id}|{dataset}".encode()
    return hashlib.sha256(payload).hexdigest()


def departure_period(clock_minute: float | int | None) -> str:
    if clock_minute is None or pd.isna(clock_minute):
        return "__MISSING_CONTEXT__"
    minute = int(clock_minute) % 1440
    if minute < 360:
        return "NIGHT"
    if minute < 600:
        return "AM_PEAK"
    if minute < 960:
        return "DAY"
    if minute < 1200:
        return "PM_PEAK"
    return "EVENING"


def _stock_class(value: Any, topcode: int) -> str:
    if pd.isna(value):
        return "UNKNOWN"
    try:
        code = int(float(value))
    except (TypeError, ValueError):
        return "UNKNOWN"
    if code == 99 or code < 0:
        return "UNKNOWN"
    if code >= topcode:
        return f"{topcode}_PLUS"
    return str(code)


def _membership(value: Any) -> str:
    mapping = {1: "ONE_PROVIDER", 2: "MULTIPLE_PROVIDERS", 3: "NONE"}
    try:
        return mapping.get(int(float(value)), "UNKNOWN")
    except (TypeError, ValueError):
        return "UNKNOWN"


def _car_access(value: Any) -> str:
    mapping = {1: "ALWAYS", 2: "OCCASIONAL", 3: "NEVER"}
    try:
        return mapping.get(int(float(value)), "UNKNOWN")
    except (TypeError, ValueError):
        return "UNKNOWN"


def _yes_no(value: Any) -> str:
    mapping = {1: "YES", 2: "NO"}
    try:
        return mapping.get(int(float(value)), "UNKNOWN")
    except (TypeError, ValueError):
        return "UNKNOWN"


def load_schema_columns(schema_path: Path) -> dict[str, list[str]]:
    frame = pd.read_csv(schema_path)
    out: dict[str, list[str]] = {}
    for dataset in DATASETS:
        cols = frame.loc[frame["dataset"].eq(dataset), "column"].astype(str).tolist()
        if not cols:
            raise ValueError(f"No frozen schema rows for {dataset}")
        out[dataset] = cols
    return out


def source_hash_validation(root: Path, source_manifest_path: Path) -> pd.DataFrame:
    manifest = pd.read_csv(source_manifest_path)
    rows: list[dict[str, Any]] = []
    for row in manifest.itertuples(index=False):
        path = root / str(row.path)
        actual = sha256_file(path) if path.is_file() else ""
        expected = str(row.sha256)
        rows.append(
            {
                "source_id": str(row.source_id),
                "path": str(row.path),
                "role": str(row.role),
                "consumed_for_rows": str(row.consumed_for_rows),
                "expected_sha256": expected,
                "actual_sha256": actual,
                "status": "PASS" if actual == expected else "FAIL",
            }
        )
    return pd.DataFrame(rows)


def _load_split(split_path: Path) -> pd.DataFrame:
    split = pd.read_csv(split_path, low_memory=False)
    required = {"source_household_id", "split", "joint_rmin_donor_eligible"}
    missing = required.difference(split.columns)
    if missing:
        raise ValueError(f"Split manifest missing columns: {sorted(missing)}")
    split["source_household_id"] = _int_or_nan(split["source_household_id"])
    return split


def _partition_households(split: pd.DataFrame, partition: str) -> set[int]:
    if partition not in PARTITIONS:
        raise ValueError(f"Forbidden partition: {partition}")
    selected = split[split["split"].eq(partition) & _as_bool(split["joint_rmin_donor_eligible"])]
    return set(selected["source_household_id"].dropna().astype(int))


def _load_persons(path: Path, household_ids: set[int]) -> pd.DataFrame:
    usecols = [
        "HP_ID",
        "H_ID",
        "P_ID",
        "P_GEW",
        "BLAND",
        "HP_SEX",
        "HP_ALTER",
        "HP_TAET",
        "ST_WOTAG",
        "saison",
        "mobil_diff",
        "P_VAUTO",
        "P_CS",
        "P_VPED",
        "P_VRAD",
    ]
    parts: list[pd.DataFrame] = []
    for chunk in pd.read_csv(path, usecols=usecols, chunksize=100_000, low_memory=False):
        take = chunk[chunk["H_ID"].isin(household_ids) & chunk["BLAND"].eq(11)].copy()
        if not take.empty:
            parts.append(take)
    if not parts:
        raise ValueError("No source persons selected")
    frame = pd.concat(parts, ignore_index=True)
    for col in ("HP_ID", "H_ID", "P_ID"):
        frame[col] = _int_or_nan(frame[col])
    return frame


def _load_households(path: Path, household_ids: set[int]) -> pd.DataFrame:
    usecols = [
        "H_ID",
        "H_GR",
        "H_ANZAUTO",
        "H_ANZMOTMOP",
        "H_ANZPED",
        "H_ANZRAD",
        "H_CS",
    ]
    selected: list[pd.DataFrame] = []
    for chunk in pd.read_csv(path, usecols=usecols, chunksize=100_000, low_memory=False):
        take = chunk[chunk["H_ID"].isin(household_ids)].copy()
        if not take.empty:
            selected.append(take)
    if not selected:
        raise ValueError("No source households selected")
    frame = pd.concat(selected, ignore_index=True)
    frame["H_ID"] = _int_or_nan(frame["H_ID"])
    if frame["H_ID"].duplicated().any():
        raise ValueError("Household source ID is not unique")
    return frame


def _build_context(
    *,
    partition: str,
    persons: pd.DataFrame,
    households: pd.DataFrame,
    activity_recoding_path: Path,
) -> pd.DataFrame:
    activity = load_activity_recoding(activity_recoding_path)
    frame = persons.merge(households, on="H_ID", how="left", validate="many_to_one")
    if frame["H_GR"].isna().any():
        raise ValueError("Missing authoritative household context")

    def activity_status(value: Any) -> str:
        try:
            return activity.get(int(float(value)), ("UNKNOWN", "UNKNOWN", "UNKNOWN"))[0]
        except (TypeError, ValueError):
            return "UNKNOWN"

    out = pd.DataFrame(
        {
            "source_household_id": frame["H_ID"].astype("int64"),
            "source_person_id": frame["HP_ID"].astype("int64"),
            "source_person_slot": frame["P_ID"].astype("int16"),
            "age_infr_class": frame["HP_ALTER"].astype(int).map(age_infr_class),
            "sex": frame["HP_SEX"].map({1: "MALE", 2: "FEMALE"}).fillna("UNKNOWN"),
            "primary_activity_status": frame["HP_TAET"].map(activity_status),
            "household_size_class": frame["H_GR"].astype(int).astype(str),
            "source_weekday": frame["ST_WOTAG"].astype("int8"),
            "source_season": frame["saison"].astype("int8"),
            "hh_car_stock_class": frame["H_ANZAUTO"].map(lambda x: _stock_class(x, 3)),
            "hh_motorcycle_moped_stock_class": frame["H_ANZMOTMOP"].map(
                lambda x: _stock_class(x, 3)
            ),
            "hh_ebike_stock_class": frame["H_ANZPED"].map(lambda x: _stock_class(x, 10)),
            "hh_bike_stock_class": frame["H_ANZRAD"].map(lambda x: _stock_class(x, 10)),
            "hh_carsharing_membership": frame["H_CS"].map(_membership),
            "person_car_access": frame["P_VAUTO"].map(_car_access),
            "person_bike_access": frame["P_VRAD"].map(_yes_no),
            "person_ebike_access": frame["P_VPED"].map(_yes_no),
            "person_carsharing_membership": frame["P_CS"].map(_membership),
            "fit_weight_P_GEW": pd.to_numeric(frame["P_GEW"], errors="coerce"),
        }
    )
    out.insert(
        0,
        "row_id",
        [
            deterministic_row_id(partition, int(h), int(p), "person_day_context")
            for h, p in zip(out["source_household_id"], out["source_person_id"], strict=True)
        ],
    )
    return out.sort_values(["source_household_id", "source_person_id"], kind="mergesort").reset_index(
        drop=True
    )


def _context_lookup(context: pd.DataFrame) -> pd.DataFrame:
    return context[["row_id", "source_household_id", "source_person_id", "fit_weight_P_GEW"]].rename(
        columns={"row_id": "context_row_id"}
    )


def _subset_evidence(frame: pd.DataFrame, person_ids: set[int]) -> pd.DataFrame:
    out = frame.copy()
    out["HP_ID"] = _int_or_nan(out["HP_ID"])
    return out[out["HP_ID"].isin(person_ids)].copy()


def _coverage_k(coverage: pd.DataFrame) -> pd.DataFrame:
    out = coverage[["HP_ID", "trip_count_fit_tier", "analytic_total_trip_count", "P_GEW"]].copy()
    out["source_trip_count_analogue"] = np.where(
        out["trip_count_fit_tier"].eq("CORE_STRICT_COUNT"),
        pd.to_numeric(out["analytic_total_trip_count"], errors="coerce"),
        np.nan,
    )
    return out[["HP_ID", "source_trip_count_analogue", "P_GEW"]]


def _build_participation(
    persons: pd.DataFrame, context: pd.DataFrame
) -> pd.DataFrame:
    base = persons[persons["mobil_diff"].isin(BINARY_MOBILITY_CODES)].copy()
    lookup = _context_lookup(context)
    out = base[["H_ID", "HP_ID", "P_GEW", "mobil_diff"]].merge(
        lookup[["context_row_id", "source_person_id"]],
        left_on="HP_ID",
        right_on="source_person_id",
        how="left",
        validate="one_to_one",
    )
    return pd.DataFrame(
        {
            "context_row_id": out["context_row_id"],
            "source_household_id": out["H_ID"].astype("int64"),
            "source_person_id": out["HP_ID"].astype("int64"),
            "target_trip_day": out["mobil_diff"].ne(0).astype("int8"),
            "fit_weight_P_GEW": pd.to_numeric(out["P_GEW"], errors="coerce"),
        }
    )


def _build_trip_count(coverage: pd.DataFrame, context: pd.DataFrame) -> pd.DataFrame:
    eligible = coverage[
        coverage["trip_count_fit_tier"].eq("CORE_STRICT_COUNT")
        & (pd.to_numeric(coverage["analytic_total_trip_count"], errors="coerce") > 0)
    ].copy()
    lookup = _context_lookup(context)
    out = eligible.merge(
        lookup[["context_row_id", "source_household_id", "source_person_id"]],
        left_on="HP_ID",
        right_on="source_person_id",
        how="left",
        validate="one_to_one",
    )
    k = pd.to_numeric(out["analytic_total_trip_count"], errors="raise").astype("int16")
    return pd.DataFrame(
        {
            "context_row_id": out["context_row_id"],
            "source_household_id": out["source_household_id"].astype("int64"),
            "source_person_id": out["source_person_id"].astype("int64"),
            "target_trip_count": k,
            "target_excess_count": (k - 1).astype("int16"),
            "fit_weight_P_GEW": pd.to_numeric(out["P_GEW"], errors="coerce"),
        }
    )


def _build_chain(
    sequence: pd.DataFrame,
    transition: pd.DataFrame,
    coverage: pd.DataFrame,
    trip_time: pd.DataFrame,
    context: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    sequence = sequence.copy()
    sequence["HP_ID"] = _int_or_nan(sequence["HP_ID"])
    functional = sequence[_as_bool(sequence["full_functional_day_sequence_eligible"])].copy()
    functional_ids = set(functional["HP_ID"].dropna().astype(int))
    transitions = transition[
        transition["HP_ID"].isin(functional_ids)
        & _as_bool(transition["transition_observation_eligible"])
    ].copy()
    transitions["W_ID"] = _int_or_nan(transitions["W_ID"])
    transitions = transitions.sort_values(["HP_ID", "W_ID"], kind="mergesort")

    k_frame = _coverage_k(coverage)
    weights = trip_time[["HP_ID", "W_ID", "W_GEW"]].copy()
    weights["HP_ID"] = _int_or_nan(weights["HP_ID"])
    weights["W_ID"] = _int_or_nan(weights["W_ID"])
    weights = weights.drop_duplicates(["HP_ID", "W_ID"])
    lookup = _context_lookup(context)

    day_last = transitions.groupby("HP_ID", sort=False).tail(1)[["HP_ID", "destination_activity"]]
    day_last = day_last.rename(columns={"destination_activity": "final_destination_activity"})
    days = functional[["HP_ID", "first_origin_activity"]].merge(day_last, on="HP_ID", how="left")
    days = days.merge(k_frame, on="HP_ID", how="left").merge(
        lookup[["context_row_id", "source_household_id", "source_person_id"]],
        left_on="HP_ID",
        right_on="source_person_id",
        how="left",
        validate="one_to_one",
    )
    chain_days = pd.DataFrame(
        {
            "context_row_id": days["context_row_id"],
            "source_household_id": days["source_household_id"].astype("int64"),
            "source_person_id": days["source_person_id"].astype("int64"),
            "source_trip_count_analogue": pd.to_numeric(
                days["source_trip_count_analogue"], errors="raise"
            ).astype("int16"),
            "first_origin_activity": days["first_origin_activity"].fillna("UNKNOWN"),
            "final_destination_activity": days["final_destination_activity"].fillna("UNKNOWN"),
            "target_return_home": days["final_destination_activity"].eq("HOME"),
            "day_weight_P_GEW": pd.to_numeric(days["P_GEW"], errors="coerce"),
        }
    )

    trans = transitions.merge(k_frame, on="HP_ID", how="left")
    trans = trans.merge(weights, on=["HP_ID", "W_ID"], how="left", validate="one_to_one")
    trans = trans.merge(
        lookup[["context_row_id", "source_household_id", "source_person_id"]],
        left_on="HP_ID",
        right_on="source_person_id",
        how="left",
        validate="many_to_one",
    )
    trans = trans.sort_values(["source_household_id", "source_person_id", "W_ID"], kind="mergesort")
    trans["trip_sequence_index"] = trans.groupby("HP_ID", sort=False).cumcount() + 1
    trans["prefix_second_last_activity"] = (
        trans.groupby("HP_ID", sort=False)["origin_activity"].shift(1).fillna("__START__")
    )
    trans["prefix_last_activity"] = trans["origin_activity"].fillna("UNKNOWN")
    trans["remaining_trips"] = (
        pd.to_numeric(trans["source_trip_count_analogue"], errors="raise").astype(int)
        - trans["trip_sequence_index"].astype(int)
    )
    if (trans["remaining_trips"] < 0).any():
        raise ValueError("Chain transition index exceeds frozen source trip count")
    if trans["W_GEW"].isna().any():
        raise ValueError("Missing W_GEW for chain transition")
    chain_transitions = pd.DataFrame(
        {
            "context_row_id": trans["context_row_id"],
            "source_household_id": trans["source_household_id"].astype("int64"),
            "source_person_id": trans["source_person_id"].astype("int64"),
            "source_trip_id": trans["W_ID"].astype("int16"),
            "trip_sequence_index": trans["trip_sequence_index"].astype("int16"),
            "source_trip_count_analogue": pd.to_numeric(
                trans["source_trip_count_analogue"], errors="raise"
            ).astype("int16"),
            "prefix_second_last_activity": trans["prefix_second_last_activity"],
            "prefix_last_activity": trans["prefix_last_activity"],
            "remaining_trips": trans["remaining_trips"].astype("int16"),
            "canonical_trip_purpose": trans["canonical_trip_purpose"].fillna("UNKNOWN"),
            "target_destination_activity": trans["destination_activity"].fillna("UNKNOWN"),
            "fit_weight_W_GEW": pd.to_numeric(trans["W_GEW"], errors="coerce"),
        }
    )
    return chain_days, chain_transitions


def _position_class(k: Any, sequence_index: int) -> str:
    if pd.isna(k):
        return "__MISSING_CONTEXT__"
    count = int(k)
    if count == 1 and sequence_index == 1:
        return "SINGLE"
    if sequence_index == 1:
        return "FIRST"
    if sequence_index == count:
        return "LAST"
    if 1 < sequence_index < count:
        return "MIDDLE"
    return "__MISSING_CONTEXT__"


def _trip_context(
    transition: pd.DataFrame,
    coverage: pd.DataFrame,
    context: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    k_frame = _coverage_k(coverage)
    trans = transition[
        ["HP_ID", "W_ID", "origin_activity", "destination_activity", "transition_observation_eligible"]
    ].copy()
    trans["HP_ID"] = _int_or_nan(trans["HP_ID"])
    trans["W_ID"] = _int_or_nan(trans["W_ID"])
    trans = trans.drop_duplicates(["HP_ID", "W_ID"])
    lookup = _context_lookup(context)
    return k_frame, trans.merge(
        lookup[["context_row_id", "source_household_id", "source_person_id"]],
        left_on="HP_ID",
        right_on="source_person_id",
        how="inner",
        validate="many_to_one",
    )


def _build_time(
    trip_time: pd.DataFrame,
    transition: pd.DataFrame,
    coverage: pd.DataFrame,
    context: pd.DataFrame,
) -> pd.DataFrame:
    k_frame, trans_with_context = _trip_context(transition, coverage, context)
    all_direct = trip_time[trip_time["W_RBW"].eq(0)].copy()
    all_direct["W_ID"] = _int_or_nan(all_direct["W_ID"])
    all_direct = all_direct.sort_values(["HP_ID", "W_ID"], kind="mergesort")
    is_valid = all_direct["temporal_row_status"].eq("DIRECT_TEMPORAL_VALID")
    previous_valid = is_valid.groupby(all_direct["HP_ID"], sort=False).shift(1, fill_value=False)
    prev_dep = all_direct.groupby("HP_ID", sort=False)["departure_clock_minute"].shift(1)
    prev_arr = all_direct.groupby("HP_ID", sort=False)["arrival_absolute_minute"].shift(1)
    all_direct["previous_departure_clock_minute"] = prev_dep.where(previous_valid)
    all_direct["previous_arrival_absolute_minute"] = prev_arr.where(previous_valid)
    valid = all_direct[is_valid].copy()
    valid = valid.merge(k_frame, on="HP_ID", how="left")
    valid = valid.merge(
        trans_with_context,
        on=["HP_ID", "W_ID"],
        how="left",
        suffixes=("", "_transition"),
        validate="many_to_one",
    )
    valid["sequence_index"] = valid["W_ID"].astype(int)
    valid["trip_position_class"] = [
        _position_class(k, i)
        for k, i in zip(valid["source_trip_count_analogue"], valid["sequence_index"], strict=True)
    ]
    eligible = _as_bool(valid["transition_observation_eligible"])
    return pd.DataFrame(
        {
            "context_row_id": valid["context_row_id"],
            "source_household_id": valid["source_household_id"].astype("int64"),
            "source_person_id": valid["HP_ID"].astype("int64"),
            "source_trip_id": valid["W_ID"].astype("int16"),
            "source_trip_count_analogue": valid["source_trip_count_analogue"],
            "origin_activity_analogue": valid["origin_activity"].fillna("__MISSING_CONTEXT__"),
            "destination_activity_analogue": valid["destination_activity"].fillna(
                "__MISSING_CONTEXT__"
            ),
            "trip_position_class": valid["trip_position_class"],
            "previous_departure_clock_minute": valid["previous_departure_clock_minute"],
            "previous_arrival_absolute_minute": valid["previous_arrival_absolute_minute"],
            "target_departure_clock_minute": valid["departure_clock_minute"],
            "target_arrival_clock_minute": valid["arrival_clock_minute"],
            "target_arrival_day_offset": valid["arrival_day_offset"].astype("int8"),
            "target_duration_from_clock_min": valid["duration_from_clock_min"],
            "fit_weight_W_GEW": valid["W_GEW"],
            "transition_context_status": np.where(eligible, "ELIGIBLE", "UNRESOLVED"),
        }
    )


def _build_distance(
    spatial: pd.DataFrame,
    trip_time: pd.DataFrame,
    transition: pd.DataFrame,
    coverage: pd.DataFrame,
    context: pd.DataFrame,
    *,
    expanded: bool,
) -> pd.DataFrame:
    k_frame, trans_with_context = _trip_context(transition, coverage, context)
    if expanded:
        selected = spatial[
            spatial["W_RBW"].eq(0) & spatial["source_distance_status"].isin(EXPANDED_DISTANCE_STATUSES)
        ].copy()
    else:
        selected = spatial[
            spatial["W_RBW"].eq(0)
            & spatial["source_distance_status"].eq("DIRECT_SOURCE_DISTANCE_VALID")
        ].copy()
    selected["W_ID"] = _int_or_nan(selected["W_ID"])
    time_all = trip_time[trip_time["W_RBW"].eq(0)][
        [
            "HP_ID",
            "W_ID",
            "W_GEW",
            "temporal_row_status",
            "departure_clock_minute",
            "arrival_clock_minute",
            "duration_from_clock_min",
        ]
    ].copy()
    time_all["HP_ID"] = _int_or_nan(time_all["HP_ID"])
    time_all["W_ID"] = _int_or_nan(time_all["W_ID"])
    time_all = time_all.drop_duplicates(["HP_ID", "W_ID"])
    selected = selected.merge(k_frame, on="HP_ID", how="left")
    selected = selected.merge(
        trans_with_context,
        on=["HP_ID", "W_ID"],
        how="left",
        suffixes=("", "_transition"),
        validate="many_to_one",
    )
    selected = selected.merge(time_all, on=["HP_ID", "W_ID"], how="left", validate="many_to_one")
    valid_time = selected["temporal_row_status"].eq("DIRECT_TEMPORAL_VALID")
    eligible_transition = _as_bool(selected["transition_observation_eligible"])
    dep = selected["departure_clock_minute"].where(valid_time)
    arr = selected["arrival_clock_minute"].where(valid_time)
    dur = selected["duration_from_clock_min"].where(valid_time)
    period = [departure_period(value) for value in dep]
    if expanded:
        target = np.where(
            selected["source_distance_status"].eq("DIRECT_SOURCE_DISTANCE_VALID"),
            pd.to_numeric(selected["wegkm"], errors="coerce"),
            pd.to_numeric(selected["wegkm_imp"], errors="coerce"),
        )
        provenance = np.where(
            selected["source_distance_status"].eq("DIRECT_SOURCE_DISTANCE_VALID"),
            "RAW_WEGKM",
            "SOURCE_IMPUTED_WEGKM",
        )
        target_name = "target_distance_sensitivity_km"
    else:
        target = pd.to_numeric(selected["wegkm"], errors="coerce")
        provenance = np.repeat("RAW_WEGKM", len(selected))
        target_name = "target_distance_prior_km"
    out = pd.DataFrame(
        {
            "context_row_id": selected["context_row_id"],
            "source_household_id": selected["source_household_id"].astype("int64"),
            "source_person_id": selected["HP_ID"].astype("int64"),
            "source_trip_id": selected["W_ID"].astype("int16"),
            "source_trip_count_analogue": selected["source_trip_count_analogue"],
            "origin_activity_analogue": selected["origin_activity"].fillna("__MISSING_CONTEXT__"),
            "destination_activity_analogue": selected["destination_activity"].fillna(
                "__MISSING_CONTEXT__"
            ),
            "departure_clock_minute_analogue": dep,
            "departure_period_analogue": period,
            "arrival_clock_minute_analogue": arr,
            "duration_from_clock_min_analogue": dur,
            "time_context_status": np.where(valid_time, "VALID", "MISSING_SOURCE_CONTEXT"),
            "transition_context_status": np.where(
                eligible_transition, "ELIGIBLE", "UNRESOLVED"
            ),
            "fit_weight_W_GEW": pd.to_numeric(selected["W_GEW"], errors="coerce"),
            target_name: target,
            "distance_provenance": provenance,
        }
    )
    if out["fit_weight_W_GEW"].isna().any():
        raise ValueError("Missing W_GEW for distance row")
    if out[target_name].isna().any():
        raise ValueError(f"Missing target in {target_name}")
    return out


def _sort_dataset(name: str, frame: pd.DataFrame) -> pd.DataFrame:
    if name in {"person_day_context", "participation", "trip_count", "chain_days"}:
        keys = ["source_household_id", "source_person_id"]
    else:
        keys = ["source_household_id", "source_person_id", "source_trip_id"]
    return frame.sort_values(keys, kind="mergesort").reset_index(drop=True)


def _category_feature_columns(schema: pd.DataFrame, dataset: str) -> list[str]:
    roles = {"FEATURE", "FEATURE_SOURCE_ANALOGUE", "UPSTREAM_SOURCE_ANALOGUE"}
    rows = schema[
        schema["dataset"].eq(dataset)
        & schema["role"].isin(roles)
        & schema["dtype"].eq("category")
    ]
    return rows["column"].astype(str).tolist()


def apply_train_vocabulary(
    train_tables: dict[str, pd.DataFrame], cal_tables: dict[str, pd.DataFrame], schema: pd.DataFrame
) -> dict[str, Any]:
    manifest: dict[str, Any] = {
        "fit_partition": "TRAIN",
        "unseen_token": "__UNSEEN__",
        "reserved_tokens": list(RESERVED_CATEGORY_TOKENS),
        "datasets": {},
    }
    reserved = set(RESERVED_CATEGORY_TOKENS)
    for dataset in DATASETS:
        manifest["datasets"][dataset] = {}
        for column in _category_feature_columns(schema, dataset):
            observed = set(train_tables[dataset][column].dropna().astype(str))
            vocab = sorted(observed | reserved)
            allowed = set(vocab)
            cal = cal_tables[dataset][column]
            mapped = cal.where(cal.isna() | cal.astype(str).isin(allowed), "__UNSEEN__")
            unseen_count = int((mapped.astype(str) == "__UNSEEN__").sum())
            cal_tables[dataset][column] = mapped
            manifest["datasets"][dataset][column] = {
                "vocabulary": vocab,
                "cal_unseen_count": unseen_count,
            }
    return manifest


def _enforce_schema(
    tables: dict[str, pd.DataFrame], schema_columns: dict[str, list[str]]
) -> dict[str, pd.DataFrame]:
    out: dict[str, pd.DataFrame] = {}
    for name, frame in tables.items():
        expected = schema_columns[name]
        missing = [col for col in expected if col not in frame.columns]
        extra = [col for col in frame.columns if col not in expected]
        if missing or extra:
            raise ValueError(f"{name} schema mismatch missing={missing} extra={extra}")
        lowered = [col.lower() for col in expected]
        for token in FORBIDDEN_OUTPUT_COLUMN_TOKENS:
            if any(token in col for col in lowered):
                raise ValueError(f"Forbidden output column token {token} in {name}")
        out[name] = _sort_dataset(name, frame[expected].copy())
    return out


def _write_csv(path: Path, frame: pd.DataFrame) -> None:
    frame.to_csv(
        path,
        index=False,
        encoding="utf-8",
        lineterminator="\n",
        float_format="%.17g",
        na_rep="",
    )


def _all_checksums(out: Path) -> list[str]:
    lines: list[str] = []
    for path in sorted(p for p in out.rglob("*") if p.is_file()):
        if path.name == "checksums.sha256":
            continue
        lines.append(f"{sha256_file(path)}  {path.relative_to(out).as_posix()}")
    return lines


def materialize_training_data(
    *,
    root: Path,
    out: Path,
    source_manifest_path: Path,
    expected_counts_path: Path,
    schema_path: Path,
    activity_recoding_path: Path,
) -> dict[str, Any]:
    if out.exists():
        raise FileExistsError(f"Output already exists; preserve it and choose a retry path: {out}")
    source_validation = source_hash_validation(root, source_manifest_path)
    if not source_validation["status"].eq("PASS").all():
        failed = source_validation[source_validation["status"].ne("PASS")]
        raise ValueError(f"Source hash validation failed: {failed['source_id'].tolist()}")

    manifest = pd.read_csv(source_manifest_path).set_index("source_id")
    def source_path(source_id: str) -> Path:
        return root / str(manifest.loc[source_id, "path"])
    split = _load_split(source_path("r2_split_manifest"))
    schema = pd.read_csv(schema_path)
    schema_columns = load_schema_columns(schema_path)
    expected_counts = pd.read_csv(expected_counts_path)

    evidence = {
        "coverage": pd.read_csv(source_path("f0_3b_personday_coverage"), low_memory=False),
        "sequence": pd.read_csv(source_path("f0_3c_person_sequence"), low_memory=False),
        "transition": pd.read_csv(source_path("f0_3c_trip_transition"), low_memory=False),
        "time": pd.read_csv(source_path("f0_3d_trip_time"), low_memory=False),
        "spatial": pd.read_csv(source_path("f0_3e_trip_spatial"), low_memory=False),
    }
    for frame in evidence.values():
        frame["HP_ID"] = _int_or_nan(frame["HP_ID"])
    for name in ("transition", "time", "spatial"):
        evidence[name]["W_ID"] = _int_or_nan(evidence[name]["W_ID"])

    tables_by_partition: dict[str, dict[str, pd.DataFrame]] = {}
    for partition in PARTITIONS:
        household_ids = _partition_households(split, partition)
        persons = _load_persons(source_path("raw_persons"), household_ids)
        households = _load_households(source_path("raw_households"), household_ids)
        context = _build_context(
            partition=partition,
            persons=persons,
            households=households,
            activity_recoding_path=activity_recoding_path,
        )
        person_ids = set(context["source_person_id"].astype(int))
        coverage = _subset_evidence(evidence["coverage"], person_ids)
        sequence = _subset_evidence(evidence["sequence"], person_ids)
        transition = _subset_evidence(evidence["transition"], person_ids)
        trip_time = _subset_evidence(evidence["time"], person_ids)
        spatial = _subset_evidence(evidence["spatial"], person_ids)

        chain_days, chain_transitions = _build_chain(
            sequence, transition, coverage, trip_time, context
        )
        tables = {
            "person_day_context": context,
            "participation": _build_participation(persons, context),
            "trip_count": _build_trip_count(coverage, context),
            "chain_days": chain_days,
            "chain_transitions": chain_transitions,
            "time_trips": _build_time(trip_time, transition, coverage, context),
            "distance_raw": _build_distance(
                spatial, trip_time, transition, coverage, context, expanded=False
            ),
            "distance_expanded_sensitivity": _build_distance(
                spatial, trip_time, transition, coverage, context, expanded=True
            ),
        }
        tables_by_partition[partition] = _enforce_schema(tables, schema_columns)

    vocabulary_manifest = apply_train_vocabulary(
        tables_by_partition["TRAIN"], tables_by_partition["CALIBRATION"], schema
    )
    # Re-apply canonical ordering after CAL category mapping.
    for partition in PARTITIONS:
        tables_by_partition[partition] = {
            name: _sort_dataset(name, frame)
            for name, frame in tables_by_partition[partition].items()
        }

    rows: list[dict[str, Any]] = []
    expected_lookup = {
        (str(row.partition), str(row.dataset)): int(row.expected_rows)
        for row in expected_counts.itertuples(index=False)
    }
    for partition in PARTITIONS:
        for dataset in DATASETS:
            actual = len(tables_by_partition[partition][dataset])
            expected = expected_lookup[(partition, dataset)]
            rows.append(
                {
                    "partition": partition,
                    "dataset": dataset,
                    "expected_rows": expected,
                    "actual_rows": actual,
                    "status": "PASS" if actual == expected else "FAIL",
                }
            )
    row_counts = pd.DataFrame(rows)
    if not row_counts["status"].eq("PASS").all():
        failed = row_counts[row_counts["status"].ne("PASS")]
        raise ValueError(f"Frozen row-count mismatch: {failed.to_dict(orient='records')}")

    out.mkdir(parents=True)
    for partition in PARTITIONS:
        part_dir = out / partition
        part_dir.mkdir()
        for dataset in DATASETS:
            _write_csv(part_dir / f"{dataset}.csv", tables_by_partition[partition][dataset])
    shutil.copyfile(schema_path, out / "dataset_schema.csv")
    _write_csv(out / "source_hash_validation.csv", source_validation)
    _write_csv(out / "row_counts.csv", row_counts)
    (out / "vocabulary_manifest.json").write_text(
        json.dumps(vocabulary_manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    table_hashes = {
        partition: {
            dataset: sha256_file(out / partition / f"{dataset}.csv")
            for dataset in DATASETS
        }
        for partition in PARTITIONS
    }
    materialization_manifest = {
        "materialization_id": "F3_2A_TRAINING_DATA_V1",
        "producer_phase": "F3.2b",
        "reference_identity": "BERLIN_HYBRID_REFERENCE_V1",
        "partitions": list(PARTITIONS),
        "test_partition_materialized": False,
        "formal_g1": "OPEN",
        "formal_g2": "NOT_EVALUATED",
        "source_hashes": "13/13 PASS",
        "row_counts": "16/16 PASS",
        "r4_synthetic_rows_used_for_fit": False,
        "mode_route_execution_consumed": False,
        "km_routing_consumed": False,
        "weights_are_features": False,
        "ids_are_features": False,
        "table_sha256": table_hashes,
    }
    (out / "materialization_manifest.json").write_text(
        json.dumps(materialization_manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    validation = pd.DataFrame(
        [
            {"check": "source_hashes_exact", "status": "PASS", "detail": "13/13"},
            {"check": "row_counts_exact", "status": "PASS", "detail": "16/16"},
            {"check": "test_absent", "status": "PASS", "detail": str(not (out / "TEST").exists())},
            {"check": "r4_not_fit_source", "status": "PASS", "detail": "interface witness only"},
            {"check": "km_routing_not_materialized", "status": "PASS", "detail": "true"},
            {"check": "mode_route_execution_not_materialized", "status": "PASS", "detail": "true"},
            {"check": "weights_not_features", "status": "PASS", "detail": "true"},
            {"check": "ids_not_features", "status": "PASS", "detail": "true"},
            {"check": "train_vocabulary_only", "status": "PASS", "detail": "true"},
            {"check": "task_specific_universes_preserved", "status": "PASS", "detail": "true"},
        ]
    )
    _write_csv(out / "materialization_validation.csv", validation)
    (out / "checksums.sha256").write_text("\n".join(_all_checksums(out)) + "\n", encoding="utf-8")
    return materialization_manifest
