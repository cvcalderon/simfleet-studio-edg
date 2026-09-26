"""Deterministic F2.2 diagnostic metric reconstruction utilities."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from simfleet_edg.common.population_materializer import age_infr_class

BINARY_MOBILITY_CODES = {0, 1, 2, 3, 5}
DIRECT_EXPANDED_DISTANCE_STATUSES = {
    "DIRECT_SOURCE_DISTANCE_VALID",
    "DIRECT_NO_DETAIL_DISTANCE_IMPUTED",
    "DIRECT_SOURCE_DISTANCE_MISSING_IMPUTED",
    "DIRECT_SOURCE_DISTANCE_IMPLAUSIBLE_IMPUTED",
}
CONDITIONAL_DIMENSIONS = (
    "age_infr_class",
    "sex",
    "primary_activity_status",
    "household_size_class",
)


@dataclass(frozen=True)
class F22Context:
    source_persons: pd.DataFrame
    coverage: pd.DataFrame
    functional: pd.DataFrame
    transition: pd.DataFrame
    trip_time: pd.DataFrame
    spatial: pd.DataFrame
    donor_pool: pd.DataFrame
    replay_persondays: pd.DataFrame
    replay_trips: pd.DataFrame
    match_persondays: pd.DataFrame
    match_trips: pd.DataFrame
    generated_persons: pd.DataFrame
    generated_households: pd.DataFrame


def _as_bool(series: pd.Series) -> pd.Series:
    if pd.api.types.is_bool_dtype(series):
        return series.fillna(False)
    return series.astype(str).str.lower().isin({"true", "1", "yes"})


def weighted_mean(values: Iterable[float], weights: Iterable[float]) -> float:
    values_arr = np.asarray(list(values), dtype=float)
    weights_arr = np.asarray(list(weights), dtype=float)
    mask = np.isfinite(values_arr) & np.isfinite(weights_arr) & (weights_arr >= 0)
    return float(np.average(values_arr[mask], weights=weights_arr[mask]))


def weighted_distribution(categories: pd.Series, weights: pd.Series) -> pd.Series:
    frame = pd.DataFrame({"category": categories.astype(str), "weight": weights.astype(float)})
    out = frame.groupby("category", sort=True, dropna=False)["weight"].sum()
    return out / out.sum()


def unweighted_distribution(categories: pd.Series) -> pd.Series:
    return categories.astype(str).value_counts(normalize=True, sort=False).sort_index()


def total_variation_distance(left: pd.Series, right: pd.Series) -> float:
    idx = left.index.union(right.index)
    left_aligned = left.reindex(idx, fill_value=0.0).astype(float)
    right_aligned = right.reindex(idx, fill_value=0.0).astype(float)
    return float(0.5 * np.abs(left_aligned - right_aligned).sum())


def weighted_quantile(values: Iterable[float], weights: Iterable[float], q: float) -> float:
    values_arr = np.asarray(list(values), dtype=float)
    weights_arr = np.asarray(list(weights), dtype=float)
    mask = np.isfinite(values_arr) & np.isfinite(weights_arr) & (weights_arr > 0)
    values_arr = values_arr[mask]
    weights_arr = weights_arr[mask]
    order = np.argsort(values_arr, kind="mergesort")
    values_arr = values_arr[order]
    weights_arr = weights_arr[order]
    cumulative = np.cumsum(weights_arr)
    pos = np.searchsorted(cumulative, q * cumulative[-1], side="left")
    return float(values_arr[pos])


def wasserstein_1d(
    values_a: Iterable[float],
    weights_a: Iterable[float],
    values_b: Iterable[float],
    weights_b: Iterable[float],
) -> float:
    a = np.asarray(list(values_a), dtype=float)
    wa = np.asarray(list(weights_a), dtype=float)
    b = np.asarray(list(values_b), dtype=float)
    wb = np.asarray(list(weights_b), dtype=float)

    ma = np.isfinite(a) & np.isfinite(wa) & (wa > 0)
    mb = np.isfinite(b) & np.isfinite(wb) & (wb > 0)
    a, wa = a[ma], wa[ma]
    b, wb = b[mb], wb[mb]

    oa = np.argsort(a, kind="mergesort")
    ob = np.argsort(b, kind="mergesort")
    a, wa = a[oa], wa[oa]
    b, wb = b[ob], wb[ob]
    wa = wa / wa.sum()
    wb = wb / wb.sum()

    support = np.sort(np.unique(np.concatenate((a, b))))
    if len(support) < 2:
        return 0.0
    lower = support[:-1]
    widths = np.diff(support)
    ca = np.cumsum(wa)
    cb = np.cumsum(wb)
    ia = np.searchsorted(a, lower, side="right") - 1
    ib = np.searchsorted(b, lower, side="right") - 1
    fa = np.where(ia >= 0, ca[np.maximum(ia, 0)], 0.0)
    fb = np.where(ib >= 0, cb[np.maximum(ib, 0)], 0.0)
    return float(np.sum(np.abs(fa - fb) * widths))


def _load_source_persons_chunked(
    raw_persons_path: Path,
    split_manifest_path: Path,
    activity_recoding_path: Path,
) -> pd.DataFrame:
    split = pd.read_csv(
        split_manifest_path,
        usecols=["source_household_id", "split", "joint_rmin_donor_eligible"],
    )
    train_households = set(
        split.loc[
            split["split"].eq("TRAIN") & _as_bool(split["joint_rmin_donor_eligible"]),
            "source_household_id",
        ].astype("int64")
    )
    usecols = [
        "HP_ID",
        "H_ID",
        "P_ID",
        "BLAND",
        "P_GEW",
        "HP_SEX",
        "HP_ALTER",
        "HP_TAET",
        "H_GR",
        "mobil_diff",
    ]
    selected: list[pd.DataFrame] = []
    for chunk in pd.read_csv(raw_persons_path, usecols=usecols, chunksize=100_000, low_memory=False):
        take = chunk[chunk["BLAND"].eq(11) & chunk["H_ID"].isin(train_households)]
        if not take.empty:
            selected.append(take)
    persons = pd.concat(selected, ignore_index=True)

    recode = pd.read_csv(activity_recoding_path).set_index("source_code")
    persons["age_infr_class"] = persons["HP_ALTER"].astype(int).map(age_infr_class)
    persons["sex"] = persons["HP_SEX"].map({1: "MALE", 2: "FEMALE"})
    persons["primary_activity_status"] = persons["HP_TAET"].map(recode["primary_activity_status"])
    persons["employment_participation"] = persons["HP_TAET"].map(recode["employment_participation"])
    persons["household_size_class"] = persons["H_GR"].clip(upper=5).astype(int)
    persons["HP_ID"] = persons["HP_ID"].astype("int64")
    persons["H_ID"] = persons["H_ID"].astype("int64")
    return persons


def load_f22_context(
    *,
    raw_persons_path: Path,
    split_manifest_path: Path,
    activity_recoding_path: Path,
    coverage_path: Path,
    functional_path: Path,
    transition_path: Path,
    trip_time_path: Path,
    spatial_path: Path,
    donor_pool_path: Path,
    replay_persondays_path: Path,
    replay_trips_path: Path,
    match_persondays_path: Path,
    match_trips_path: Path,
    generated_persons_path: Path,
    generated_households_path: Path,
) -> F22Context:
    persons = _load_source_persons_chunked(raw_persons_path, split_manifest_path, activity_recoding_path)
    source_ids = set(persons["HP_ID"].astype(int))

    coverage = pd.read_csv(coverage_path, low_memory=False)
    functional = pd.read_csv(functional_path, low_memory=False)
    transition = pd.read_csv(transition_path, low_memory=False)
    trip_time = pd.read_csv(trip_time_path, low_memory=False)
    spatial = pd.read_csv(spatial_path, low_memory=False)
    for frame in (coverage, functional, transition, trip_time, spatial):
        frame["HP_ID"] = pd.to_numeric(frame["HP_ID"], errors="coerce").astype("Int64")
    for frame in (transition, trip_time, spatial):
        frame["W_ID"] = pd.to_numeric(frame["W_ID"], errors="coerce").astype("Int64")
    coverage = coverage[coverage["HP_ID"].isin(source_ids)].copy()
    functional = functional[functional["HP_ID"].isin(source_ids)].copy()
    transition = transition[transition["HP_ID"].isin(source_ids)].copy()
    trip_time = trip_time[trip_time["HP_ID"].isin(source_ids)].copy()
    spatial = spatial[spatial["HP_ID"].isin(source_ids)].copy()

    trip_weights = trip_time[["HP_ID", "W_ID", "W_GEW"]]
    transition = transition.merge(trip_weights, on=["HP_ID", "W_ID"], how="left")
    spatial = spatial.merge(trip_weights, on=["HP_ID", "W_ID"], how="left")

    return F22Context(
        source_persons=persons,
        coverage=coverage,
        functional=functional,
        transition=transition,
        trip_time=trip_time,
        spatial=spatial,
        donor_pool=pd.read_csv(donor_pool_path, low_memory=False),
        replay_persondays=pd.read_csv(replay_persondays_path, low_memory=False),
        replay_trips=pd.read_csv(replay_trips_path, low_memory=False),
        match_persondays=pd.read_csv(match_persondays_path, low_memory=False),
        match_trips=pd.read_csv(match_trips_path, low_memory=False),
        generated_persons=pd.read_csv(generated_persons_path, low_memory=False),
        generated_households=pd.read_csv(generated_households_path, low_memory=False),
    )


def reference_frames(ctx: F22Context) -> dict[str, pd.DataFrame]:
    persons = ctx.source_persons
    binary = persons[persons["mobil_diff"].isin(BINARY_MOBILITY_CODES)].copy()
    binary["trip_day"] = binary["mobil_diff"].ne(0).astype(int)

    count = ctx.coverage[ctx.coverage["trip_count_fit_tier"].eq("CORE_STRICT_COUNT")].copy()
    count = count.merge(persons[["HP_ID", *CONDITIONAL_DIMENSIONS]], on="HP_ID", how="left")
    count_mobile = count[count["analytic_total_trip_count"].gt(0)].copy()

    purpose = ctx.transition[
        ctx.transition["W_RBW"].eq(0) & _as_bool(ctx.transition["purpose_marginal_eligible"])
    ].copy()
    timing = ctx.trip_time[ctx.trip_time["temporal_row_status"].eq("DIRECT_TEMPORAL_VALID")].copy()
    transition = ctx.transition[_as_bool(ctx.transition["transition_observation_eligible"])].copy()
    transition["activity_transition"] = (
        transition["origin_activity"].astype(str) + ">" + transition["destination_activity"].astype(str)
    )

    raw_distance = ctx.spatial[
        ctx.spatial["W_RBW"].eq(0)
        & ctx.spatial["source_distance_status"].eq("DIRECT_SOURCE_DISTANCE_VALID")
    ].copy()
    expanded_distance = ctx.spatial[
        ctx.spatial["W_RBW"].eq(0)
        & ctx.spatial["source_distance_status"].isin(DIRECT_EXPANDED_DISTANCE_STATUSES)
    ].copy()
    expanded_distance["distance_km"] = np.where(
        expanded_distance["source_distance_status"].eq("DIRECT_SOURCE_DISTANCE_VALID"),
        expanded_distance["wegkm"],
        expanded_distance["wegkm_imp"],
    )

    full_functional = ctx.functional[_as_bool(ctx.functional["full_functional_day_sequence_eligible"])].copy()
    last_transition = (
        transition.sort_values(["HP_ID", "W_ID"])
        .groupby("HP_ID", sort=False)
        .tail(1)[["HP_ID", "destination_activity"]]
    )
    full_functional = full_functional.merge(
        persons[["HP_ID", "P_GEW"]], on="HP_ID", how="left"
    ).merge(last_transition, on="HP_ID", how="left")

    donor_ids = set(ctx.donor_pool["HP_ID"].astype(int))
    donor_purpose = purpose[purpose["HP_ID"].isin(donor_ids)].copy()
    donor_timing = timing[timing["HP_ID"].isin(donor_ids)].copy()
    donor_transition = transition[transition["HP_ID"].isin(donor_ids)].copy()
    donor_raw_distance = raw_distance[raw_distance["HP_ID"].isin(donor_ids)].copy()
    donor_expanded_distance = expanded_distance[expanded_distance["HP_ID"].isin(donor_ids)].copy()

    donor_mobile_ids = set(
        ctx.donor_pool.loc[ctx.donor_pool["analytic_total_trip_count"].gt(0), "HP_ID"].astype(int)
    )
    donor_last = last_transition[last_transition["HP_ID"].isin(donor_mobile_ids)].copy()
    donor_return = ctx.donor_pool[ctx.donor_pool["HP_ID"].isin(donor_mobile_ids)][["HP_ID", "P_GEW"]].merge(
        donor_last, on="HP_ID", how="left"
    )

    return {
        "REF_TRAIN_BINARY": binary,
        "REF_TRAIN_CORE_STRICT_COUNT": count,
        "REF_TRAIN_CORE_STRICT_COUNT_MOBILE": count_mobile,
        "REF_TRAIN_DIRECT_PURPOSE": purpose,
        "REF_TRAIN_DIRECT_TIME_VALID": timing,
        "REF_TRAIN_TRANSITION": transition,
        "REF_TRAIN_DISTANCE_RAW": raw_distance,
        "REF_TRAIN_DISTANCE_EXPANDED": expanded_distance,
        "REF_TRAIN_FULL_FUNCTIONAL": full_functional,
        "REF_FULLDAY_POOL": ctx.donor_pool.copy(),
        "REF_FULLDAY_POOL_PURPOSE": donor_purpose,
        "REF_FULLDAY_POOL_TIME": donor_timing,
        "REF_FULLDAY_POOL_TRANSITION": donor_transition,
        "REF_FULLDAY_POOL_DISTANCE_RAW": donor_raw_distance,
        "REF_FULLDAY_POOL_DISTANCE_EXPANDED": donor_expanded_distance,
        "REF_FULLDAY_POOL_RETURN": donor_return,
    }


def _trip_count_category(series: pd.Series) -> pd.Series:
    numeric = pd.to_numeric(series, errors="raise")
    return numeric.map(lambda x: "12_PLUS" if x >= 12 else str(int(x)))


def _hour_category(series: pd.Series) -> pd.Series:
    return (pd.to_numeric(series, errors="raise") // 60).astype(int).astype(str)


def _transition_category(frame: pd.DataFrame) -> pd.Series:
    return frame["origin_activity"].astype(str) + ">" + frame["destination_activity"].astype(str)


def build_distribution_detail(ctx: F22Context, refs: dict[str, pd.DataFrame]) -> pd.DataFrame:
    rows: list[dict[str, object]] = []

    ref_count = refs["REF_TRAIN_CORE_STRICT_COUNT"]
    replay_count_ids = set(ref_count["HP_ID"].astype(int))
    replay_count = ctx.replay_persondays[
        pd.to_numeric(ctx.replay_persondays["diary_source_hp_id"], errors="coerce").isin(replay_count_ids)
    ].copy()
    datasets_count = [
        ("REF_TRAIN_CORE_STRICT_COUNT", weighted_distribution(_trip_count_category(ref_count["analytic_total_trip_count"]), ref_count["P_GEW"])),
        ("REF_FULLDAY_POOL", weighted_distribution(_trip_count_category(ctx.donor_pool["analytic_total_trip_count"]), ctx.donor_pool["P_GEW"])),
        ("D_REPLAY_EXACT_V1", unweighted_distribution(_trip_count_category(replay_count["analytic_total_trip_count"]))),
        ("D_MATCH_FULLDAY_V1", unweighted_distribution(_trip_count_category(ctx.match_persondays["analytic_total_trip_count"]))),
    ]
    for dataset, dist in datasets_count:
        for category, share in dist.items():
            rows.append({"metric_id": "M2-COUNT-02", "dimension": "trip_count", "dataset": dataset, "category": category, "share": float(share)})

    source_mobile = refs["REF_TRAIN_CORE_STRICT_COUNT_MOBILE"]
    donor_mobile = ctx.donor_pool[ctx.donor_pool["analytic_total_trip_count"].gt(0)]
    replay_mobile = replay_count[replay_count["analytic_total_trip_count"].gt(0)]
    match_mobile = ctx.match_persondays[ctx.match_persondays["analytic_total_trip_count"].gt(0)]
    datasets_chain = [
        ("REF_TRAIN_CORE_STRICT_COUNT_MOBILE", weighted_distribution(_trip_count_category(source_mobile["analytic_total_trip_count"]), source_mobile["P_GEW"])),
        ("REF_FULLDAY_POOL_MOBILE", weighted_distribution(_trip_count_category(donor_mobile["analytic_total_trip_count"]), donor_mobile["P_GEW"])),
        ("D_REPLAY_EXACT_V1", unweighted_distribution(_trip_count_category(replay_mobile["analytic_total_trip_count"]))),
        ("D_MATCH_FULLDAY_V1", unweighted_distribution(_trip_count_category(match_mobile["analytic_total_trip_count"]))),
    ]
    for dataset, dist in datasets_chain:
        for category, share in dist.items():
            rows.append({"metric_id": "M2-CHAIN-01", "dimension": "mobile_chain_length", "dataset": dataset, "category": category, "share": float(share)})

    datasets_purpose = [
        ("REF_TRAIN_DIRECT_PURPOSE", weighted_distribution(refs["REF_TRAIN_DIRECT_PURPOSE"]["canonical_trip_purpose"], refs["REF_TRAIN_DIRECT_PURPOSE"]["W_GEW"])),
        ("REF_FULLDAY_POOL_TRIPS", weighted_distribution(refs["REF_FULLDAY_POOL_PURPOSE"]["canonical_trip_purpose"], refs["REF_FULLDAY_POOL_PURPOSE"]["W_GEW"])),
        ("D_REPLAY_EXACT_V1", unweighted_distribution(ctx.replay_trips["canonical_trip_purpose"])),
        ("D_MATCH_FULLDAY_V1", unweighted_distribution(ctx.match_trips["canonical_trip_purpose"])),
    ]
    for dataset, dist in datasets_purpose:
        for category, share in dist.items():
            rows.append({"metric_id": "M2-PURP-01", "dimension": "purpose", "dataset": dataset, "category": category, "share": float(share)})

    datasets_time = [
        ("REF_TRAIN_DIRECT_TIME_VALID", weighted_distribution(_hour_category(refs["REF_TRAIN_DIRECT_TIME_VALID"]["departure_clock_minute"]), refs["REF_TRAIN_DIRECT_TIME_VALID"]["W_GEW"])),
        ("REF_FULLDAY_POOL_TRIPS", weighted_distribution(_hour_category(refs["REF_FULLDAY_POOL_TIME"]["departure_clock_minute"]), refs["REF_FULLDAY_POOL_TIME"]["W_GEW"])),
        ("D_REPLAY_EXACT_V1", unweighted_distribution(_hour_category(ctx.replay_trips["departure_clock_minute"]))),
        ("D_MATCH_FULLDAY_V1", unweighted_distribution(_hour_category(ctx.match_trips["departure_clock_minute"]))),
    ]
    for dataset, dist in datasets_time:
        for category, share in dist.items():
            rows.append({"metric_id": "M2-TIME-01", "dimension": "departure_hour", "dataset": dataset, "category": category, "share": float(share)})

    datasets_transition = [
        ("REF_TRAIN_TRANSITION", weighted_distribution(refs["REF_TRAIN_TRANSITION"]["activity_transition"], refs["REF_TRAIN_TRANSITION"]["W_GEW"])),
        ("REF_FULLDAY_POOL_TRIPS", weighted_distribution(refs["REF_FULLDAY_POOL_TRANSITION"]["activity_transition"], refs["REF_FULLDAY_POOL_TRANSITION"]["W_GEW"])),
        ("D_REPLAY_EXACT_V1", unweighted_distribution(_transition_category(ctx.replay_trips))),
        ("D_MATCH_FULLDAY_V1", unweighted_distribution(_transition_category(ctx.match_trips))),
    ]
    for dataset, dist in datasets_transition:
        for category, share in dist.items():
            rows.append({"metric_id": "M2-TRANS-01", "dimension": "activity_transition", "dataset": dataset, "category": category, "share": float(share)})

    return pd.DataFrame(rows, columns=["metric_id", "dimension", "dataset", "category", "share"])


def _distribution_from_detail(detail: pd.DataFrame, metric_id: str, dataset: str) -> pd.Series:
    sub = detail[(detail["metric_id"] == metric_id) & (detail["dataset"] == dataset)]
    return sub.set_index("category")["share"].astype(float)


def _unweighted_quantile(series: pd.Series, q: float) -> float:
    return float(pd.to_numeric(series, errors="raise").quantile(q, interpolation="linear"))


def build_global_metrics(ctx: F22Context, refs: dict[str, pd.DataFrame], detail: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []

    def add(metric_id: str, family: str, variant: str, reference: str, statistic: str, value: float, reference_value: float, unit: str, role: str, notes: str | None = None) -> None:
        rows.append({
            "metric_id": metric_id,
            "family": family,
            "variant": variant,
            "reference": reference,
            "statistic": statistic,
            "value": float(value),
            "reference_value": float(reference_value) if not pd.isna(reference_value) else np.nan,
            "delta": float(value - reference_value) if not pd.isna(reference_value) else np.nan,
            "unit": unit,
            "role": role,
            "notes": notes,
        })

    binary = refs["REF_TRAIN_BINARY"]
    ref_part = weighted_mean(binary["trip_day"], binary["P_GEW"])
    donor_part = weighted_mean(ctx.donor_pool["analytic_total_trip_count"].gt(0).astype(int), ctx.donor_pool["P_GEW"])
    replay_binary = ctx.replay_persondays[ctx.replay_persondays["participation_class"].isin(["TRIP_DAY", "NO_TRIP"])]
    replay_part = float(replay_binary["participation_class"].eq("TRIP_DAY").mean())
    match_part = float(ctx.match_persondays["participation_class"].eq("TRIP_DAY").mean())
    add("M2-PART-01", "Participation", "REF_FULLDAY_POOL", "REF_TRAIN_BINARY", "trip_day_share", donor_part, ref_part, "share", "DIAGNOSTIC", "Selection-pool diagnostic, not target.")
    add("M2-PART-01", "Participation", "D_REPLAY_EXACT_V1", "REF_TRAIN_BINARY", "trip_day_share", replay_part, ref_part, "share", "DIAGNOSTIC", f"Coverage={len(replay_binary)}/100000.")
    add("M2-PART-01", "Participation", "D_MATCH_FULLDAY_V1", "REF_TRAIN_BINARY", "trip_day_share", match_part, ref_part, "share", "DIAGNOSTIC", "Conditioned on full-day donor pool.")

    count = refs["REF_TRAIN_CORE_STRICT_COUNT"]
    ref_count_mean = weighted_mean(count["analytic_total_trip_count"], count["P_GEW"])
    donor_count_mean = weighted_mean(ctx.donor_pool["analytic_total_trip_count"], ctx.donor_pool["P_GEW"])
    count_ids = set(count["HP_ID"].astype(int))
    replay_count = ctx.replay_persondays[pd.to_numeric(ctx.replay_persondays["diary_source_hp_id"], errors="coerce").isin(count_ids)]
    replay_count_mean = float(replay_count["analytic_total_trip_count"].mean())
    match_count_mean = float(ctx.match_persondays["analytic_total_trip_count"].mean())
    add("M2-COUNT-01", "TripCount", "REF_FULLDAY_POOL", "REF_TRAIN_CORE_STRICT_COUNT", "mean_trips_per_person_day", donor_count_mean, ref_count_mean, "trips/person-day", "DIAGNOSTIC", "Selection-pool diagnostic.")
    add("M2-COUNT-01", "TripCount", "D_REPLAY_EXACT_V1", "REF_TRAIN_CORE_STRICT_COUNT", "mean_trips_per_person_day", replay_count_mean, ref_count_mean, "trips/person-day", "DIAGNOSTIC", f"Coverage={len(replay_count)}/100000.")
    add("M2-COUNT-01", "TripCount", "D_MATCH_FULLDAY_V1", "REF_TRAIN_CORE_STRICT_COUNT", "mean_trips_per_person_day", match_count_mean, ref_count_mean, "trips/person-day", "DIAGNOSTIC", "All 100k matched days.")

    for metric_id, family, ref_dataset, variants in [
        ("M2-COUNT-02", "TripCount", "REF_TRAIN_CORE_STRICT_COUNT", ["REF_FULLDAY_POOL", "D_REPLAY_EXACT_V1", "D_MATCH_FULLDAY_V1"]),
        ("M2-CHAIN-01", "Chain", "REF_TRAIN_CORE_STRICT_COUNT_MOBILE", ["REF_FULLDAY_POOL_MOBILE", "D_REPLAY_EXACT_V1", "D_MATCH_FULLDAY_V1"]),
        ("M2-PURP-01", "Purpose", "REF_TRAIN_DIRECT_PURPOSE", ["REF_FULLDAY_POOL_TRIPS", "D_REPLAY_EXACT_V1", "D_MATCH_FULLDAY_V1"]),
        ("M2-TIME-01", "Timing", "REF_TRAIN_DIRECT_TIME_VALID", ["REF_FULLDAY_POOL_TRIPS", "D_REPLAY_EXACT_V1", "D_MATCH_FULLDAY_V1"]),
    ]:
        ref_dist = _distribution_from_detail(detail, metric_id, ref_dataset)
        for variant in variants:
            value = total_variation_distance(_distribution_from_detail(detail, metric_id, variant), ref_dist)
            add(metric_id, family, variant, ref_dataset, "TVD", value, 0.0, "TVD", "DIAGNOSTIC")

    full_func = refs["REF_TRAIN_FULL_FUNCTIONAL"]
    ref_return = weighted_mean(full_func["destination_activity"].eq("HOME").astype(int), full_func["P_GEW"])
    donor_return = refs["REF_FULLDAY_POOL_RETURN"]
    donor_return_share = weighted_mean(donor_return["destination_activity"].eq("HOME").astype(int), donor_return["P_GEW"])
    replay_mobile = ctx.replay_persondays[ctx.replay_persondays["plan_status"].eq("COMPLETE_MOBILE_DAY")]
    match_mobile = ctx.match_persondays[ctx.match_persondays["plan_status"].eq("COMPLETE_MOBILE_DAY")]

    def synthetic_return(persondays: pd.DataFrame, trips: pd.DataFrame) -> float:
        last = trips.sort_values(["person_day_id", "trip_sequence_index"]).groupby("person_day_id", sort=False).tail(1)[["person_day_id", "destination_activity"]]
        merged = persondays[["person_day_id"]].merge(last, on="person_day_id", how="inner")
        return float(merged["destination_activity"].eq("HOME").mean())

    add("M2-RET-01", "Chain", "REF_FULLDAY_POOL_MOBILE", "REF_TRAIN_FULL_FUNCTIONAL", "return_home_share", donor_return_share, ref_return, "share", "DIAGNOSTIC", "Selection pool.")
    add("M2-RET-01", "Chain", "D_REPLAY_EXACT_V1", "REF_TRAIN_FULL_FUNCTIONAL", "return_home_share", synthetic_return(replay_mobile, ctx.replay_trips), ref_return, "share", "DIAGNOSTIC", "Complete replay mobile days only.")
    add("M2-RET-01", "Chain", "D_MATCH_FULLDAY_V1", "REF_TRAIN_FULL_FUNCTIONAL", "return_home_share", synthetic_return(match_mobile, ctx.match_trips), ref_return, "share", "DIAGNOSTIC", "Matched mobile days only.")

    ref_trans = _distribution_from_detail(detail, "M2-TRANS-01", "REF_TRAIN_TRANSITION")
    for variant in ["REF_FULLDAY_POOL_TRIPS", "D_REPLAY_EXACT_V1", "D_MATCH_FULLDAY_V1"]:
        add("M2-TRANS-01", "Sequence", variant, "REF_TRAIN_TRANSITION", "TVD", total_variation_distance(_distribution_from_detail(detail, "M2-TRANS-01", variant), ref_trans), 0.0, "TVD", "DIAGNOSTIC")

    def add_distance_family(metric_id: str, reference_name: str, ref_frame: pd.DataFrame, donor_frame: pd.DataFrame, role: str, raw_only: bool) -> None:
        ref_values = ref_frame["wegkm"] if raw_only else ref_frame["distance_km"]
        ref_weights = ref_frame["W_GEW"]
        ref_stats = {
            "mean": weighted_mean(ref_values, ref_weights),
            "p50": weighted_quantile(ref_values, ref_weights, 0.50),
            "p90": weighted_quantile(ref_values, ref_weights, 0.90),
            "p95": weighted_quantile(ref_values, ref_weights, 0.95),
        }
        variants: list[tuple[str, pd.Series, pd.Series]] = []
        donor_values = donor_frame["wegkm"] if raw_only else donor_frame["distance_km"]
        variants.append(("REF_FULLDAY_POOL_TRIPS", donor_values, donor_frame["W_GEW"]))
        for name, trips in [("D_REPLAY_EXACT_V1", ctx.replay_trips), ("D_MATCH_FULLDAY_V1", ctx.match_trips)]:
            if raw_only:
                selected = trips[trips["source_distance_status"].eq("DIRECT_SOURCE_DISTANCE_VALID")]
            else:
                selected = trips
            variants.append((name, selected["distance_prior_km"], pd.Series(np.ones(len(selected)), index=selected.index)))
        for name, values, weights in variants:
            weighted = name == "REF_FULLDAY_POOL_TRIPS"
            stats = {
                "mean": weighted_mean(values, weights) if weighted else float(pd.to_numeric(values).mean()),
                "p50": weighted_quantile(values, weights, 0.50) if weighted else _unweighted_quantile(values, 0.50),
                "p90": weighted_quantile(values, weights, 0.90) if weighted else _unweighted_quantile(values, 0.90),
                "p95": weighted_quantile(values, weights, 0.95) if weighted else _unweighted_quantile(values, 0.95),
                "Wasserstein": wasserstein_1d(ref_values, ref_weights, values, weights),
            }
            for stat in ["mean", "p50", "p90", "p95"]:
                add(metric_id, "Distance", name, reference_name, stat, stats[stat], ref_stats[stat], "km", role)
            add(metric_id, "Distance", name, reference_name, "Wasserstein", stats["Wasserstein"], 0.0, "km", role)

    add_distance_family("M2-DIST-01", "REF_TRAIN_DISTANCE_RAW", refs["REF_TRAIN_DISTANCE_RAW"], refs["REF_FULLDAY_POOL_DISTANCE_RAW"], "DIAGNOSTIC", True)
    add_distance_family("M2-DIST-02", "REF_TRAIN_DISTANCE_EXPANDED", refs["REF_TRAIN_DISTANCE_EXPANDED"], refs["REF_FULLDAY_POOL_DISTANCE_EXPANDED"], "SENSITIVITY", False)

    donor_counts = ctx.match_persondays["diary_source_hp_id"].value_counts()
    unique_donors = int(donor_counts.size)
    shares = donor_counts.astype(float) / donor_counts.sum()
    effective = float(1.0 / np.square(shares).sum())
    top10 = float(shares.nlargest(10).sum())
    add("M2-DIAG-DONOR-01", "Matching", "D_MATCH_FULLDAY_V1", "FULLDAY_DIARY_POOL", "unique_diary_donors_used", unique_donors, len(ctx.donor_pool), "donors", "REPORT_ONLY", "Repeated matching does not create new empirical diary diversity.")
    add("M2-DIAG-DONOR-02", "Matching", "D_MATCH_FULLDAY_V1", "FULLDAY_DIARY_POOL", "effective_donor_count_inverse_simpson", effective, len(ctx.donor_pool), "effective donors", "REPORT_ONLY", "Concentration measure under 100k assignments.")
    rows[-1]["delta"] = effective - len(ctx.donor_pool)
    rows.append({
        "metric_id": "M2-DIAG-DONOR-03",
        "family": "Matching",
        "variant": "D_MATCH_FULLDAY_V1",
        "reference": "FULLDAY_DIARY_POOL",
        "statistic": "top10_donor_assignment_share",
        "value": top10,
        "reference_value": np.nan,
        "delta": np.nan,
        "unit": "share",
        "role": "REPORT_ONLY",
        "notes": "Concentration of matched assignments.",
    })
    return pd.DataFrame(rows, columns=["metric_id", "family", "variant", "reference", "statistic", "value", "reference_value", "delta", "unit", "role", "notes"])


def build_conditional_metrics(ctx: F22Context, refs: dict[str, pd.DataFrame]) -> pd.DataFrame:
    generated = ctx.generated_persons[["person_id", "household_id", "age_infr_class", "sex", "primary_activity_status"]].copy()
    hh_static = ctx.generated_households[["household_id", "household_size_class"]].copy()
    generated = generated.merge(hh_static, on="household_id", how="left")
    replay_p = ctx.replay_persondays.merge(generated, left_on="generated_person_id", right_on="person_id", how="left")
    match_p = ctx.match_persondays.merge(generated, left_on="generated_person_id", right_on="person_id", how="left")
    replay_part = replay_p[replay_p["participation_class"].isin(["TRIP_DAY", "NO_TRIP"])].copy()
    match_part = match_p.copy()
    count_ref = refs["REF_TRAIN_CORE_STRICT_COUNT"]
    count_ids = set(count_ref["HP_ID"].astype(int))
    replay_count = replay_p[pd.to_numeric(replay_p["diary_source_hp_id"], errors="coerce").isin(count_ids)].copy()
    match_count = match_p.copy()
    source_binary = refs["REF_TRAIN_BINARY"]

    rows: list[dict[str, object]] = []
    for dim in CONDITIONAL_DIMENSIONS:
        # Preserve the historical source-defined group universe and lexical ordering.
        for metric_id, source, synthetic_a, synthetic_b, unit in [
            ("M2-COND-01", source_binary, replay_part, match_part, "share"),
            ("M2-COND-02", count_ref, replay_count, match_count, "trips/person-day"),
        ]:
            groups = sorted(source[dim].dropna().astype(str).unique())
            # historical universes coincide within each dimension; use source for each metric
            for group in groups:
                src = source[source[dim].astype(str).eq(group)]
                if metric_id == "M2-COND-01":
                    ref_value = weighted_mean(src["trip_day"], src["P_GEW"])
                else:
                    ref_value = weighted_mean(src["analytic_total_trip_count"], src["P_GEW"])
                support = "OK" if len(src) >= 30 else "LOW_N"
                for variant, synth in [("D_REPLAY_EXACT_V1", synthetic_a), ("D_MATCH_FULLDAY_V1", synthetic_b)]:
                    sub = synth[synth[dim].astype(str).eq(group)]
                    if metric_id == "M2-COND-01":
                        value = float(sub["participation_class"].eq("TRIP_DAY").mean())
                    else:
                        value = float(sub["analytic_total_trip_count"].mean())
                    rows.append({
                        "metric_id": metric_id,
                        "group_dimension": dim,
                        "group_value": group,
                        "variant": variant,
                        "source_n": int(len(src)),
                        "synthetic_n": int(len(sub)),
                        "reference_value": ref_value,
                        "value": value,
                        "delta": value - ref_value,
                        "unit": unit,
                        "support_status": support,
                    })
    return pd.DataFrame(rows, columns=["metric_id", "group_dimension", "group_value", "variant", "source_n", "synthetic_n", "reference_value", "value", "delta", "unit", "support_status"])


def build_selection_bias_audit(ctx: F22Context, refs: dict[str, pd.DataFrame], global_metrics: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for dim in CONDITIONAL_DIMENSIONS:
        value = total_variation_distance(
            weighted_distribution(ctx.donor_pool[dim], ctx.donor_pool["P_GEW"]),
            weighted_distribution(ctx.source_persons[dim], ctx.source_persons["P_GEW"]),
        )
        rows.append({
            "dimension": dim,
            "comparison": "REF_FULLDAY_POOL_vs_ALL_STRICT_TRAIN_PERSONS",
            "statistic": "TVD",
            "value": value,
            "notes": "Quantifies static selection associated with requiring a complete M2 diary.",
        })

    def metric(metric_id: str, variant: str, statistic: str) -> float:
        row = global_metrics[(global_metrics["metric_id"] == metric_id) & (global_metrics["variant"] == variant) & (global_metrics["statistic"] == statistic)].iloc[0]
        return float(row["value"])

    rows.extend([
        {"dimension": "participation", "comparison": "REF_FULLDAY_POOL_vs_REF_TRAIN_BINARY", "statistic": "trip_day_share_pp_difference", "value": 100.0 * float(global_metrics[(global_metrics.metric_id == "M2-PART-01") & (global_metrics.variant == "REF_FULLDAY_POOL")].iloc[0]["delta"]), "notes": "Completeness-selection effect plus differing eligibility universes."},
        {"dimension": "trip_count", "comparison": "REF_FULLDAY_POOL_vs_REF_TRAIN_CORE_STRICT_COUNT", "statistic": "mean_trips_per_day_difference", "value": float(global_metrics[(global_metrics.metric_id == "M2-COUNT-01") & (global_metrics.variant == "REF_FULLDAY_POOL")].iloc[0]["delta"]), "notes": "Completeness-selection effect."},
        {"dimension": "purpose", "comparison": "REF_FULLDAY_POOL_TRIPS_vs_REF_TRAIN_DIRECT_PURPOSE", "statistic": "TVD", "value": metric("M2-PURP-01", "REF_FULLDAY_POOL_TRIPS", "TVD"), "notes": "Trip-level distribution shift induced by complete-diary selection."},
        {"dimension": "departure_hour", "comparison": "REF_FULLDAY_POOL_TRIPS_vs_REF_TRAIN_DIRECT_TIME_VALID", "statistic": "TVD", "value": metric("M2-TIME-01", "REF_FULLDAY_POOL_TRIPS", "TVD"), "notes": "Trip-level timing shift induced by complete-diary selection."},
        {"dimension": "activity_transition", "comparison": "REF_FULLDAY_POOL_TRIPS_vs_REF_TRAIN_TRANSITION", "statistic": "TVD", "value": metric("M2-TRANS-01", "REF_FULLDAY_POOL_TRIPS", "TVD"), "notes": "Sequence shift induced by complete-diary selection."},
    ])
    return pd.DataFrame(rows, columns=["dimension", "comparison", "statistic", "value", "notes"])
