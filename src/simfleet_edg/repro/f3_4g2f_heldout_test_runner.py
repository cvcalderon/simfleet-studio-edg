from __future__ import annotations

import argparse
import hashlib
import json
import platform
import subprocess
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import yaml

from simfleet_edg.demand.time_schedule import validate_temporal_row
from simfleet_edg.demand.training_data import (
    DATASETS,
    _as_bool,
    _build_chain,
    _build_context,
    _build_distance,
    _build_participation,
    _build_time,
    _build_trip_count,
    _enforce_schema,
    _load_households,
    _load_persons,
    _load_split,
    _sort_dataset,
    _subset_evidence,
    _write_csv,
    load_schema_columns,
)
from simfleet_edg.evaluation.activity_chain_purpose_attribution import (
    attribute_generated_purpose,
)
from simfleet_edg.evaluation.cal_harness import (
    evaluation_person_id,
    packed_draw_index,
)
from simfleet_edg.evaluation.cal_metrics import (
    total_variation_distance,
    weighted_distribution,
    weighted_mean,
)
from simfleet_edg.evaluation.cal_protocol import runtime_draw_seed
from simfleet_edg.evaluation.cal_state import (
    propagated_chain_state,
    propagated_distance_state,
    propagated_time_state,
)
from simfleet_edg.evaluation.time_schedule_cal_real import (
    _reference_full_chain_thresholds,
)
from simfleet_edg.repro import f3_4g2c_joint_real_cal as joint_cal
from simfleet_edg.repro.f3_4g2a_joint_synthetic import (
    FORBIDDEN_STATIC,
    JointAdapters,
    _chain_frame,
    _frame,
    _sample_time,
    load_pipeline,
)
from simfleet_edg.repro.f3_4g2e_test_auth import (
    load_heldout_test_authorization,
)

REPO_ROOT = Path.cwd()
JOINT_REGISTRY = REPO_ROOT / "configs/f3/f3_4g1_joint_pipeline_registry_v1.json"
METRIC_MATRIX = REPO_ROOT / "docs/F3_4G1_JOINT_METRIC_MATRIX_v1.csv"
COND_DIMS = (
    "age_infr_class",
    "sex",
    "primary_activity_status",
    "household_size_class",
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def write_recursive_checksums(output: Path) -> None:
    target = output / "checksums.sha256"
    rows: list[str] = []
    for path in sorted(p for p in output.rglob("*") if p.is_file()):
        if path == target:
            continue
        rows.append(
            f"{sha256_file(path)}  {path.relative_to(output).as_posix()}"
        )
    target.write_text("\n".join(rows) + "\n", encoding="utf-8")


def _source_path(
    repo_root: Path,
    source_manifest: pd.DataFrame,
    source_id: str,
) -> Path:
    return repo_root / str(source_manifest.loc[source_id, "path"])


def _test_households(split: pd.DataFrame) -> set[int]:
    selected = split[
        split["split"].eq("TEST")
        & _as_bool(split["joint_rmin_donor_eligible"])
    ]
    return set(selected["source_household_id"].dropna().astype(int))


def source_hash_validation_with_consumption(
    root: Path,
    source_manifest_path: Path,
    staging: Path,
) -> pd.DataFrame:
    """Validate frozen sources and mark consumption after first content block."""
    manifest = pd.read_csv(source_manifest_path)
    rows: list[dict[str, Any]] = []
    marker = staging / "holdout_consumption.json"
    marker_written = False

    for row in manifest.itertuples(index=False):
        path = root / str(row.path)
        expected = str(row.sha256)
        actual = ""

        if path.is_file():
            digest = hashlib.sha256()
            with path.open("rb") as handle:
                first = handle.read(1024 * 1024)
                if first:
                    if not marker_written:
                        write_json(
                            marker,
                            {
                                "phase": "F3.4g-2f",
                                "holdout_consumed": True,
                                "trigger": (
                                    "FIRST_PROTECTED_SOURCE_CONTENT_BLOCK_READ"
                                ),
                                "first_source_id": str(row.source_id),
                                "first_source_path": str(row.path),
                                "same_holdout_rerun_authorized": False,
                                "main_review_required_after_failure": True,
                            },
                        )
                        marker_written = True
                    digest.update(first)

                for block in iter(
                    lambda: handle.read(1024 * 1024),
                    b"",
                ):
                    if block and not marker_written:
                        write_json(
                            marker,
                            {
                                "phase": "F3.4g-2f",
                                "holdout_consumed": True,
                                "trigger": (
                                    "FIRST_PROTECTED_SOURCE_CONTENT_BLOCK_READ"
                                ),
                                "first_source_id": str(row.source_id),
                                "first_source_path": str(row.path),
                                "same_holdout_rerun_authorized": False,
                                "main_review_required_after_failure": True,
                            },
                        )
                        marker_written = True
                    digest.update(block)

            actual = digest.hexdigest()

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


def apply_frozen_train_vocabulary(
    tables: dict[str, pd.DataFrame],
    vocabulary: dict[str, Any],
) -> dict[str, Any]:
    if vocabulary.get("fit_partition") != "TRAIN":
        raise ValueError("Frozen vocabulary must be TRAIN-fitted")
    unseen = str(vocabulary.get("unseen_token"))
    if unseen != "__UNSEEN__":
        raise ValueError("Unexpected frozen unseen token")

    report: dict[str, Any] = {
        "fit_partition": "TRAIN",
        "unseen_token": unseen,
        "datasets": {},
    }
    dataset_specs = vocabulary.get("datasets", {})
    for dataset in DATASETS:
        report["datasets"][dataset] = {}
        for column, spec in dataset_specs.get(dataset, {}).items():
            if column not in tables[dataset].columns:
                raise ValueError(
                    f"Vocabulary column absent from {dataset}: {column}"
                )
            allowed = set(map(str, spec["vocabulary"]))
            series = tables[dataset][column]
            mapped = series.where(
                series.isna() | series.astype(str).isin(allowed),
                unseen,
            )
            unseen_count = int((mapped.astype(str) == unseen).sum())
            tables[dataset][column] = mapped
            report["datasets"][dataset][column] = {
                "test_unseen_count": unseen_count,
                "vocabulary_size": len(allowed),
            }
    return report


def materialize_heldout_test(
    repo_root: Path,
    staging: Path,
    cfg: dict[str, Any],
) -> tuple[dict[str, pd.DataFrame], pd.DataFrame, dict[str, Any]]:
    materializer = cfg["materializer_reuse"]
    source_manifest_path = repo_root / str(materializer["source_manifest"])
    schema_path = repo_root / str(materializer["schema"])
    activity_path = repo_root / str(materializer["activity_recoding"])

    source_validation = source_hash_validation_with_consumption(
        repo_root,
        source_manifest_path,
        staging,
    )
    if not source_validation["status"].eq("PASS").all():
        failed = source_validation.loc[
            source_validation["status"].ne("PASS"),
            "source_id",
        ].astype(str).tolist()
        raise ValueError(f"Source hash validation failed: {failed}")

    source_manifest = pd.read_csv(source_manifest_path).set_index("source_id")
    split = _load_split(
        _source_path(repo_root, source_manifest, "r2_split_manifest")
    )
    household_ids = _test_households(split)
    expected_households = int(cfg["split_identity"]["strict_rmin_households"])
    if len(household_ids) != expected_households:
        raise ValueError(
            f"TEST household count mismatch: {len(household_ids)} "
            f"!= {expected_households}"
        )

    persons = _load_persons(
        _source_path(repo_root, source_manifest, "raw_persons"),
        household_ids,
    )
    households = _load_households(
        _source_path(repo_root, source_manifest, "raw_households"),
        household_ids,
    )
    context = _build_context(
        partition="TEST",
        persons=persons,
        households=households,
        activity_recoding_path=activity_path,
    )
    context_households = set(context["source_household_id"].astype(int))
    if context_households != household_ids:
        raise ValueError("TEST context household membership mismatch")

    evidence = {
        "coverage": pd.read_csv(
            _source_path(
                repo_root,
                source_manifest,
                "f0_3b_personday_coverage",
            ),
            low_memory=False,
        ),
        "sequence": pd.read_csv(
            _source_path(
                repo_root,
                source_manifest,
                "f0_3c_person_sequence",
            ),
            low_memory=False,
        ),
        "transition": pd.read_csv(
            _source_path(
                repo_root,
                source_manifest,
                "f0_3c_trip_transition",
            ),
            low_memory=False,
        ),
        "time": pd.read_csv(
            _source_path(
                repo_root,
                source_manifest,
                "f0_3d_trip_time",
            ),
            low_memory=False,
        ),
        "spatial": pd.read_csv(
            _source_path(
                repo_root,
                source_manifest,
                "f0_3e_trip_spatial",
            ),
            low_memory=False,
        ),
    }

    person_ids = set(context["source_person_id"].astype(int))
    for name, frame in evidence.items():
        frame["HP_ID"] = pd.to_numeric(
            frame["HP_ID"],
            errors="coerce",
        ).astype("Int64")
        evidence[name] = _subset_evidence(frame, person_ids)

    for name in ("transition", "time", "spatial"):
        evidence[name]["W_ID"] = pd.to_numeric(
            evidence[name]["W_ID"],
            errors="coerce",
        ).astype("Int64")

    chain_days, chain_transitions = _build_chain(
        evidence["sequence"],
        evidence["transition"],
        evidence["coverage"],
        evidence["time"],
        context,
    )
    tables = {
        "person_day_context": context,
        "participation": _build_participation(persons, context),
        "trip_count": _build_trip_count(evidence["coverage"], context),
        "chain_days": chain_days,
        "chain_transitions": chain_transitions,
        "time_trips": _build_time(
            evidence["time"],
            evidence["transition"],
            evidence["coverage"],
            context,
        ),
        "distance_raw": _build_distance(
            evidence["spatial"],
            evidence["time"],
            evidence["transition"],
            evidence["coverage"],
            context,
            expanded=False,
        ),
        "distance_expanded_sensitivity": _build_distance(
            evidence["spatial"],
            evidence["time"],
            evidence["transition"],
            evidence["coverage"],
            context,
            expanded=True,
        ),
    }

    schema_columns = load_schema_columns(schema_path)
    tables = _enforce_schema(tables, schema_columns)

    vocab_snapshot = json.loads(
        (
            repo_root
            / str(
                materializer["frozen_train_vocabulary"]["semantic_snapshot"]
            )
        ).read_text(encoding="utf-8")
    )
    runtime_vocab = json.loads(
        (
            repo_root
            / str(materializer["frozen_train_vocabulary"]["runtime_path"])
        ).read_text(encoding="utf-8")
    )
    if runtime_vocab != vocab_snapshot:
        raise ValueError("Runtime TRAIN vocabulary differs from frozen snapshot")
    vocab_report = apply_frozen_train_vocabulary(tables, vocab_snapshot)

    tables = {
        name: _sort_dataset(name, frame)
        for name, frame in tables.items()
    }

    materialized = staging / str(
        cfg["runbundle"]["materialized_test_subdir"]
    )
    materialized.mkdir()
    row_rows: list[dict[str, Any]] = []
    table_hashes: dict[str, str] = {}

    for dataset in DATASETS:
        frame = tables[dataset]
        if frame.empty:
            raise ValueError(f"TEST dataset unexpectedly empty: {dataset}")
        if not set(frame["source_household_id"].astype(int)) <= household_ids:
            raise ValueError(f"TEST household leakage in {dataset}")
        path = materialized / f"{dataset}.csv"
        _write_csv(path, frame)
        table_hashes[dataset] = sha256_file(path)
        row_rows.append(
            {
                "partition": "TEST",
                "dataset": dataset,
                "actual_rows": len(frame),
                "status": "PASS",
            }
        )

    row_counts = pd.DataFrame(row_rows)
    source_validation.to_csv(
        staging / "source_hash_validation.csv",
        index=False,
    )
    row_counts.to_csv(staging / "test_row_counts.csv", index=False)
    write_json(
        staging / "test_vocabulary_application.json",
        vocab_report,
    )

    materialization_manifest = {
        "materialization_id": "F3_4G2F_HELDOUT_TEST_MATERIALIZATION_V1",
        "partition": "TEST",
        "split_seed": int(cfg["split_identity"]["split_seed"]),
        "strict_rmin_households": len(household_ids),
        "source_hashes": "13/13 PASS",
        "test_row_counts_are_observed_once_not_tuned_targets": True,
        "train_vocabulary_reused": True,
        "test_vocabulary_fit": False,
        "test_unseen_mapping": "__UNSEEN__",
        "table_sha256": table_hashes,
        "row_counts": {
            row["dataset"]: int(row["actual_rows"])
            for row in row_rows
        },
    }
    write_json(
        staging / "test_materialization_manifest.json",
        materialization_manifest,
    )
    return tables, source_validation, materialization_manifest


def generate_test_pipeline(
    label: str,
    adapters: JointAdapters,
    cohort: pd.DataFrame,
    *,
    replicates: int,
    master_seed: int,
    scenario_id: str,
    purpose_artifact: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, int]]:
    day_rows: list[dict[str, Any]] = []
    trip_rows: list[dict[str, Any]] = []
    violations = {
        "structural": 0,
        "temporal": 0,
        "distance": 0,
        "nofuture": 0,
    }

    max_k = int(np.max(adapters.trip_count.support))
    reference_thresholds = (
        _reference_full_chain_thresholds(adapters.time, max_k)
        if adapters.time.record.candidate_id == "TIME_REF"
        else None
    )

    for replicate in range(replicates):
        for _, day in cohort.iterrows():
            static = {
                key: value
                for key, value in day.to_dict().items()
                if key
                not in {
                    "row_id",
                    "source_household_id",
                    "source_person_id",
                }
            }
            if FORBIDDEN_STATIC & set(static):
                violations["nofuture"] += 1

            person_id = evaluation_person_id(
                day["source_household_id"],
                day["source_person_id"],
            )
            part_seed = runtime_draw_seed(
                master_seed,
                scenario_id,
                person_id,
                "DG_PARTICIPATION",
                packed_draw_index(replicate, 0),
            )
            part = adapters.participation.sample_one(
                _frame(
                    static,
                    list(adapters.participation.required_columns),
                ),
                seed=part_seed,
            )

            trip_day = bool(part["trip_day"])
            trip_count = 0
            activities: list[str] = []
            temporal_ok = True
            distance_ok = True

            if trip_day:
                count_seed = runtime_draw_seed(
                    master_seed,
                    scenario_id,
                    person_id,
                    "DG_TRIP_COUNT",
                    packed_draw_index(replicate, 0),
                )
                count = adapters.trip_count.sample_one(
                    _frame(
                        static,
                        list(adapters.trip_count.required_columns),
                    ),
                    seed=count_seed,
                )
                trip_count = int(count["trip_count"])
                if trip_count < 1:
                    violations["structural"] += 1
                    trip_count = 0

            if trip_count > 0:
                init_seed = runtime_draw_seed(
                    master_seed,
                    scenario_id,
                    person_id,
                    "DG_ACTIVITY_CHAIN",
                    packed_draw_index(replicate, 0),
                )
                activities = [
                    adapters.chain.sample_initial_activity(seed=init_seed)
                ]

                for trip_index in range(1, trip_count + 1):
                    chain_state = propagated_chain_state(
                        static,
                        trip_count=trip_count,
                        prefix=activities,
                        remaining_trips=trip_count - trip_index,
                    )
                    transition_seed = runtime_draw_seed(
                        master_seed,
                        scenario_id,
                        person_id,
                        "DG_ACTIVITY_CHAIN",
                        packed_draw_index(
                            replicate,
                            2 * trip_index - 1,
                        ),
                    )
                    sampled = adapters.chain.sample_transition(
                        _chain_frame(adapters.chain, chain_state),
                        seed=transition_seed,
                    )
                    destination = str(sampled["next_activity"])

                    activities.append(destination)

                if len(activities) != trip_count + 1:
                    violations["structural"] += 1

                previous_departure: int | None = None
                previous_arrival: int | None = None

                for trip_index in range(1, trip_count + 1):
                    time_state = propagated_time_state(
                        static,
                        trip_count=trip_count,
                        trip_index=trip_index,
                        origin_activity=activities[trip_index - 1],
                        destination_activity=activities[trip_index],
                        previous_departure_clock_minute=previous_departure,
                        previous_arrival_absolute_minute=previous_arrival,
                    )
                    time_seed = runtime_draw_seed(
                        master_seed,
                        scenario_id,
                        str(day["row_id"]),
                        f"DG_TIME_SCHEDULE::TRIP::{trip_index}",
                        replicate,
                    )
                    time_result = _sample_time(
                        adapters.time,
                        time_state,
                        previous_arrival=previous_arrival,
                        trips_remaining=trip_count - trip_index,
                        seed=time_seed,
                        reference_thresholds=reference_thresholds,
                    )
                    ok, validated = validate_temporal_row(
                        time_result["departure_clock_minute"],
                        time_result["duration_from_clock_min"],
                        previous_arrival_absolute_minute=previous_arrival,
                        trips_remaining_after_current=(
                            trip_count - trip_index
                        ),
                    )
                    if not ok:
                        violations["temporal"] += 1
                        temporal_ok = False
                        break

                    departure = int(validated["departure_clock_minute"])
                    arrival = int(validated["arrival_absolute_minute"])
                    duration = int(validated["duration_from_clock_min"])
                    previous_departure = departure
                    previous_arrival = arrival

                    distance_state = propagated_distance_state(
                        static,
                        trip_count=trip_count,
                        origin_activity=activities[trip_index - 1],
                        destination_activity=activities[trip_index],
                        departure_clock_minute=departure,
                        arrival_absolute_minute=arrival,
                        duration_from_clock_minute=duration,
                    )
                    distance_seed = runtime_draw_seed(
                        master_seed,
                        scenario_id,
                        str(day["row_id"]),
                        f"DG_DISTANCE_PRIOR::TRIP::{trip_index}",
                        replicate,
                    )
                    distance = adapters.distance.sample_one(
                        pd.DataFrame([distance_state]),
                        seed=distance_seed,
                    )
                    distance_km = float(distance["distance_prior_km"])
                    if not np.isfinite(distance_km) or distance_km <= 0:
                        violations["distance"] += 1
                        distance_ok = False
                        break

                    purpose_seed = runtime_draw_seed(
                        master_seed,
                        scenario_id,
                        person_id,
                        "DG_ACTIVITY_CHAIN",
                        packed_draw_index(replicate, 2 * trip_index),
                    )
                    chain_state = propagated_chain_state(
                        static,
                        trip_count=trip_count,
                        prefix=activities[:trip_index],
                        remaining_trips=trip_count - trip_index,
                    )
                    purpose_state = {
                        **chain_state,
                        "target_destination_activity": activities[trip_index],
                    }
                    generated_purpose = attribute_generated_purpose(
                        purpose_artifact,
                        purpose_state,
                        u=float(
                            np.random.default_rng(purpose_seed).random()
                        ),
                    )

                    trip_rows.append(
                        {
                            "pipeline": label,
                            "replicate_index": replicate,
                            "row_id": day["row_id"],
                            "source_household_id": day[
                                "source_household_id"
                            ],
                            "source_person_id": day["source_person_id"],
                            "trip_index": trip_index,
                            "trip_count": trip_count,
                            "origin_activity": activities[trip_index - 1],
                            "destination_activity": activities[trip_index],
                            "generated_purpose": generated_purpose,
                            "departure_clock_minute": departure,
                            "arrival_absolute_minute": arrival,
                            "duration_from_clock_min": duration,
                            "distance_prior_km": distance_km,
                        }
                    )

            day_rows.append(
                {
                    "pipeline": label,
                    "replicate_index": replicate,
                    "row_id": day["row_id"],
                    "source_household_id": day["source_household_id"],
                    "source_person_id": day["source_person_id"],
                    "trip_day": trip_day,
                    "trip_count": trip_count,
                    "final_activity": activities[-1] if activities else "",
                    "return_home": bool(
                        activities and activities[-1] == "HOME"
                    ),
                    "temporal_chain_valid": temporal_ok,
                    "distance_chain_valid": distance_ok,
                }
            )

    return day_rows, trip_rows, violations


def participation_metrics(
    participation: pd.DataFrame,
    context: pd.DataFrame,
    generated_days: pd.DataFrame,
    pipeline: str,
) -> dict[str, float]:
    merged = joint_cal._merge_target_context(
        participation,
        context,
        target_name="participation",
        validate="one_to_one",
    )
    observed = merged["target_trip_day"].astype(int).to_numpy()
    weights = merged["fit_weight_P_GEW_target"].astype(float).to_numpy()
    ids = merged["context_row_id"].astype(str).tolist()
    draws = joint_cal._day_matrix(
        generated_days,
        pipeline,
        ids,
        "trip_day",
    ).astype(int)

    observed_global = joint_cal._weighted_share(observed, weights)
    global_errors: list[float] = []
    subgroup_errors: list[float] = []

    for replicate in range(32):
        generated = draws[replicate]
        global_errors.append(
            abs(
                joint_cal._weighted_share(generated, weights)
                - observed_global
            )
        )
        supported: list[float] = []
        for dimension in COND_DIMS:
            values = merged[dimension].astype(str).to_numpy()
            for group in sorted(set(values.tolist())):
                mask = values == group
                if int(mask.sum()) < 30:
                    continue
                obs = joint_cal._weighted_share(
                    observed[mask],
                    weights[mask],
                )
                gen = joint_cal._weighted_share(
                    generated[mask],
                    weights[mask],
                )
                supported.append(abs(gen - obs))
        if not supported:
            raise ValueError(
                "No supported TEST Participation conditional cells"
            )
        subgroup_errors.append(max(supported))

    return {
        "M2-PART-01": float(np.mean(global_errors)),
        "M2-COND-01": float(np.mean(subgroup_errors)),
    }


def _build_count_universe(
    participation: pd.DataFrame,
    trip_count: pd.DataFrame,
    context: pd.DataFrame,
) -> pd.DataFrame:
    part = joint_cal._merge_target_context(
        participation,
        context,
        target_name="participation",
        validate="one_to_one",
    )
    count = joint_cal._merge_target_context(
        trip_count,
        context,
        target_name="trip_count",
        validate="one_to_one",
    )
    mobile_ids = set(
        part.loc[
            part["target_trip_day"].astype(int).eq(1),
            "context_row_id",
        ].astype(str)
    )
    count_map = dict(
        zip(
            count["context_row_id"].astype(str),
            count["target_trip_count"].astype(int),
            strict=True,
        )
    )
    if not set(count_map) <= mobile_ids:
        raise ValueError("TEST Trip Count targets must be mobile days")

    evaluable = part.loc[
        part["target_trip_day"].astype(int).eq(0)
        | part["context_row_id"].astype(str).isin(count_map)
    ].copy()
    observed: list[int] = []
    for _, row in evaluable.iterrows():
        context_id = str(row["context_row_id"])
        observed.append(
            0
            if int(row["target_trip_day"]) == 0
            else int(count_map[context_id])
        )
    evaluable["observed_trip_count_full"] = observed
    return evaluable


def trip_count_metrics(
    participation: pd.DataFrame,
    trip_count: pd.DataFrame,
    context: pd.DataFrame,
    generated_days: pd.DataFrame,
    pipeline: str,
) -> dict[str, float]:
    full = _build_count_universe(participation, trip_count, context)
    ids = full["context_row_id"].astype(str).tolist()
    draws = joint_cal._day_matrix(
        generated_days,
        pipeline,
        ids,
        "trip_count",
    ).astype(int)
    observed = full["observed_trip_count_full"].astype(int).to_numpy()
    weights = full["fit_weight_P_GEW_target"].astype(float).to_numpy()
    mean_obs = float(np.average(observed, weights=weights))

    mean_errors: list[float] = []
    tvd_all: list[float] = []
    tvd_mobile: list[float] = []
    conditional: list[float] = []

    for replicate in range(32):
        generated = draws[replicate]
        mean_errors.append(
            abs(
                float(np.average(generated, weights=weights))
                - mean_obs
            )
        )
        tvd_all.append(
            joint_cal._count_tvd(
                observed,
                generated,
                weights,
                mobile_only=False,
            )
        )
        tvd_mobile.append(
            joint_cal._count_tvd(
                observed,
                generated,
                weights,
                mobile_only=True,
            )
        )

        supported: list[float] = []
        for dimension in COND_DIMS:
            values = full[dimension].astype(str).to_numpy()
            for group in sorted(set(values.tolist())):
                mask = values == group
                if int(mask.sum()) < 30:
                    continue
                obs = float(
                    np.average(observed[mask], weights=weights[mask])
                )
                gen = float(
                    np.average(generated[mask], weights=weights[mask])
                )
                supported.append(abs(gen - obs))
        if not supported:
            raise ValueError(
                "No supported TEST Trip Count conditional cells"
            )
        conditional.append(max(supported))

    return {
        "M2-COUNT-01": float(np.mean(mean_errors)),
        "M2-COUNT-02": float(np.mean(tvd_all)),
        "M2-CHAIN-01": float(np.mean(tvd_mobile)),
        "M2-COND-02": float(np.mean(conditional)),
    }


def chain_metrics(
    chain_days: pd.DataFrame,
    chain_transitions: pd.DataFrame,
    context: pd.DataFrame,
    generated_days: pd.DataFrame,
    generated_trips: pd.DataFrame,
    pipeline: str,
) -> dict[str, float]:
    days = joint_cal._merge_target_context(
        chain_days,
        context,
        target_name="chain_days",
        validate="one_to_one",
    )
    transitions = joint_cal._merge_target_context(
        chain_transitions,
        context,
        target_name="chain_transitions",
        validate="many_to_one",
    )
    observed_purpose = weighted_distribution(
        transitions["canonical_trip_purpose"],
        transitions["fit_weight_W_GEW"],
    )
    observed_transition = weighted_distribution(
        transitions["prefix_last_activity"].astype(str)
        + "->"
        + transitions["target_destination_activity"].astype(str),
        transitions["fit_weight_W_GEW"],
    )
    observed_return = weighted_mean(
        days["target_return_home"].astype(int),
        days["day_weight_P_GEW"],
    )

    day_ids = set(days["context_row_id"].astype(str))
    day_weights = dict(
        zip(
            days["context_row_id"].astype(str),
            days["day_weight_P_GEW"].astype(float),
            strict=True,
        )
    )
    purpose_errors: list[float] = []
    transition_errors: list[float] = []
    return_errors: list[float] = []

    for replicate in range(32):
        trips = generated_trips.loc[
            generated_trips["pipeline"].eq(pipeline)
            & generated_trips["replicate_index"].astype(int).eq(replicate)
            & generated_trips["row_id"].astype(str).isin(day_ids)
        ].copy()
        if trips.empty:
            raise ValueError(
                "Generated TEST chain transition denominator is zero"
            )
        weights = np.asarray(
            [day_weights[str(value)] for value in trips["row_id"]],
            dtype=float,
        )
        generated_purpose = weighted_distribution(
            trips["generated_purpose"],
            weights,
        )
        generated_transition = weighted_distribution(
            trips["origin_activity"].astype(str)
            + "->"
            + trips["destination_activity"].astype(str),
            weights,
        )

        day_rep = generated_days.loc[
            generated_days["pipeline"].eq(pipeline)
            & generated_days["replicate_index"].astype(int).eq(replicate)
            & generated_days["row_id"].astype(str).isin(day_ids)
            & generated_days["trip_count"].astype(int).gt(0)
        ].copy()
        if day_rep.empty:
            raise ValueError(
                "Generated TEST functional-mobile-day denominator is zero"
            )
        return_weights = np.asarray(
            [day_weights[str(value)] for value in day_rep["row_id"]],
            dtype=float,
        )
        generated_return = weighted_mean(
            day_rep["return_home"].astype(int),
            return_weights,
        )

        purpose_errors.append(
            total_variation_distance(
                observed_purpose,
                generated_purpose,
            )
        )
        transition_errors.append(
            total_variation_distance(
                observed_transition,
                generated_transition,
            )
        )
        return_errors.append(
            abs(float(generated_return) - float(observed_return))
        )

    return {
        "M2-PURP-01": float(np.mean(purpose_errors)),
        "M2-TRANS-01": float(np.mean(transition_errors)),
        "M2-RET-01": float(np.mean(return_errors)),
    }


def compute_pipeline_metrics(
    frames: dict[str, pd.DataFrame],
    generated_days: pd.DataFrame,
    generated_trips: pd.DataFrame,
    pipeline: str,
) -> dict[str, float]:
    context = frames["person_day_context"]
    metrics: dict[str, float] = {}
    metrics.update(
        participation_metrics(
            frames["participation"],
            context,
            generated_days,
            pipeline,
        )
    )
    metrics.update(
        trip_count_metrics(
            frames["participation"],
            frames["trip_count"],
            context,
            generated_days,
            pipeline,
        )
    )
    metrics.update(
        chain_metrics(
            frames["chain_days"],
            frames["chain_transitions"],
            context,
            generated_days,
            generated_trips,
            pipeline,
        )
    )
    metrics.update(
        joint_cal.time_metrics(
            frames["time_trips"],
            context,
            generated_trips,
            pipeline,
        )
    )
    metrics.update(
        joint_cal.distance_metrics(
            frames["distance_raw"],
            frames["distance_expanded_sensitivity"],
            context,
            generated_trips,
            pipeline,
        )
    )
    return metrics


def _g2_decision(
    metric_rows: pd.DataFrame,
    *,
    structural: int,
    temporal: int,
    nofuture: int,
    artifact_manifests_frozen: bool,
) -> dict[str, Any]:
    decision = metric_rows.loc[
        metric_rows["decision_role"].ne("REPORT_ONLY")
    ].copy()
    metric_pass = bool(decision["gate_pass"].astype(bool).all())

    checks = {
        "structural_invariant_violations_zero": structural == 0,
        "temporal_invariant_violations_zero": temporal == 0,
        "nofuture_violations_zero": nofuture == 0,
        "all_14_decision_metrics_pass": (
            len(decision) == 14 and metric_pass
        ),
        "ten_artifact_slots_frozen": artifact_manifests_frozen,
        "no_post_test_design_change": True,
    }
    failed = [name for name, passed in checks.items() if not passed]
    return {
        "formal_g2": "PASS" if not failed else "FAIL",
        "checks": checks,
        "failed": failed,
        "decision_metrics_pass": int(
            decision["gate_pass"].astype(bool).sum()
        ),
        "decision_metrics_total": len(decision),
        "report_only_metrics": int(
            metric_rows["decision_role"].eq("REPORT_ONLY").sum()
        ),
        "scientific_fail_is_valid_execution": bool(failed),
        "same_holdout_tuning_authorized": False,
        "same_holdout_rerun_authorized": False,
    }


def _run_direct(
    repo_root: Path,
    staging: Path,
    config_path: Path,
    authorization: dict[str, Any],
) -> dict[str, Any]:
    cfg = yaml.safe_load(config_path.read_text(encoding="utf-8"))

    frames, source_validation, materialization = materialize_heldout_test(
        repo_root,
        staging,
        cfg,
    )

    registry = json.loads(JOINT_REGISTRY.read_text(encoding="utf-8"))
    selected, selected_validation = load_pipeline(
        repo_root,
        list(registry["selected_pipeline"]),
    )
    reference, reference_validation = load_pipeline(
        repo_root,
        list(registry["all_reference_pipeline"]),
    )
    artifact_validation = pd.DataFrame(
        [
            {"pipeline": "SELECTED", **row}
            for row in selected_validation
        ]
        + [
            {"pipeline": "ALL_REFERENCE", **row}
            for row in reference_validation
        ]
    )

    purpose_spec = cfg["activity_chain"]["purpose_artifact"]
    purpose_path = repo_root / str(purpose_spec["path"])
    if sha256_file(purpose_path) != str(purpose_spec["sha256"]):
        raise ValueError("Purpose artifact SHA mismatch")
    purpose_artifact = json.loads(purpose_path.read_text(encoding="utf-8"))

    context = frames["person_day_context"]
    replicates = int(cfg["execution"]["stochastic_replicates"])
    master_seed = int(cfg["execution"]["master_seed"])
    scenario_id = str(cfg["execution"]["scenario_id"])

    selected_days, selected_trips, selected_violations = (
        generate_test_pipeline(
            "SELECTED",
            selected,
            context,
            replicates=replicates,
            master_seed=master_seed,
            scenario_id=scenario_id,
            purpose_artifact=purpose_artifact,
        )
    )
    reference_days, reference_trips, reference_violations = (
        generate_test_pipeline(
            "ALL_REFERENCE",
            reference,
            context,
            replicates=replicates,
            master_seed=master_seed,
            scenario_id=scenario_id,
            purpose_artifact=purpose_artifact,
        )
    )
    generated_days = pd.DataFrame(selected_days + reference_days)
    generated_trips = pd.DataFrame(selected_trips + reference_trips)

    selected_metrics = compute_pipeline_metrics(
        frames,
        generated_days,
        generated_trips,
        "SELECTED",
    )
    reference_metrics = compute_pipeline_metrics(
        frames,
        generated_days,
        generated_trips,
        "ALL_REFERENCE",
    )
    metric_rows, _ = joint_cal.build_joint_metric_rows(
        selected_metrics,
        reference_metrics,
    )

    structural = (
        int(selected_violations["structural"])
        + int(reference_violations["structural"])
        + int(selected_violations["distance"])
        + int(reference_violations["distance"])
    )
    temporal = (
        int(selected_violations["temporal"])
        + int(reference_violations["temporal"])
    )
    nofuture = (
        int(selected_violations["nofuture"])
        + int(reference_violations["nofuture"])
    )
    manifests_frozen = bool(
        len(artifact_validation) == 10
        and artifact_validation["status"].eq("PASS").all()
    )
    g2 = _g2_decision(
        metric_rows,
        structural=structural,
        temporal=temporal,
        nofuture=nofuture,
        artifact_manifests_frozen=manifests_frozen,
    )
    g2.update(
        {
            "structural_invariant_violations": structural,
            "temporal_invariant_violations": temporal,
            "nofuture_violations": nofuture,
        }
    )

    execution_checks = {
        "source_hashes_13_pass": (
            len(source_validation) == 13
            and source_validation["status"].eq("PASS").all()
        ),
        "strict_test_households_260": (
            int(materialization["strict_rmin_households"]) == 260
        ),
        "eight_materialized_test_tables": (
            len(materialization["table_sha256"]) == 8
        ),
        "artifact_slots_10": len(artifact_validation) == 10,
        "artifact_validation_all_pass": artifact_validation[
            "status"
        ].eq("PASS").all(),
        "generated_days_nonempty": not generated_days.empty,
        "generated_trips_nonempty": not generated_trips.empty,
        "metric_rows_17": len(metric_rows) == 17,
        "decision_metrics_14": (
            metric_rows["decision_role"].ne("REPORT_ONLY").sum() == 14
        ),
        "candidate_selection_none": (
            cfg["execution"]["candidate_selection"] == "NONE"
        ),
        "holdout_consumed": True,
    }
    validation = pd.DataFrame(
        [
            {
                "check": name,
                "status": "PASS" if bool(value) else "FAIL",
            }
            for name, value in execution_checks.items()
        ]
    )
    if not validation["status"].eq("PASS").all():
        failed = validation.loc[
            validation["status"].eq("FAIL"),
            "check",
        ].astype(str).tolist()
        raise RuntimeError(
            f"TEST execution integrity validation failed: {failed}"
        )

    artifact_validation.to_csv(
        staging / "pipeline_artifact_validation.csv",
        index=False,
    )
    generated_days.to_csv(staging / "generated_days.csv", index=False)
    generated_trips.to_csv(staging / "generated_trips.csv", index=False)
    metric_rows.to_csv(staging / "test_metrics.csv", index=False)
    validation.to_csv(staging / "validation.csv", index=False)
    pd.DataFrame(
        columns=["issue_id", "severity", "detail"]
    ).to_csv(staging / "issues.csv", index=False)

    write_json(staging / "authorization_snapshot.json", authorization)
    write_json(
        staging / "contract_snapshot.json",
        {
            "phase": "F3.4g-2f",
            "test_protocol_commit": cfg["frozen_test_protocol"][
                "authoritative_commit"
            ],
            "split_sha256": cfg["split_identity"]["sha256"],
            "test_scenario_id": scenario_id,
            "test_master_seed": master_seed,
            "metric_matrix_sha256": cfg["metrics"]["matrix_sha256"],
            "train_vocabulary_reused": True,
            "candidate_selection": "NONE",
            "post_test_tuning": "FORBIDDEN",
        },
    )
    write_json(staging / "g2_decision.json", g2)
    write_json(
        staging / "environment.json",
        {
            "python": sys.version,
            "platform": platform.platform(),
            "numpy": np.__version__,
            "pandas": pd.__version__,
        },
    )

    implementation_commit = subprocess.check_output(
        ["git", "rev-parse", "HEAD"],
        cwd=repo_root,
        text=True,
    ).strip()
    manifest = {
        "phase": "F3.4g-2f",
        "component": "DGEN_JOINT_PIPELINE",
        "mode": "CONTROLLED_HELDOUT_TEST",
        "status": "PASS",
        "implementation_commit": implementation_commit,
        "holdout_consumed": True,
        "strict_test_households": 260,
        "materialized_test_row_counts": materialization["row_counts"],
        "pipeline_artifact_slots": len(artifact_validation),
        "stochastic_replicates": replicates,
        "test_master_seed": master_seed,
        "test_scenario_id": scenario_id,
        "generated_day_rows": len(generated_days),
        "generated_trip_rows": len(generated_trips),
        "candidate_selection": "NONE",
        "formal_g2": g2["formal_g2"],
        "g2_decision_metrics_pass": g2["decision_metrics_pass"],
        "g2_decision_metrics_total": g2["decision_metrics_total"],
        "same_holdout_rerun_authorized": False,
        "post_test_tuning_authorized": False,
    }
    write_json(staging / "run_manifest.json", manifest)
    write_recursive_checksums(staging)
    return manifest


def run_controlled_heldout_test(
    repo_root: Path,
    output_dir: Path,
    config_path: Path,
    authorization_path: Path,
) -> dict[str, Any]:
    authorization = load_heldout_test_authorization(
        authorization_path,
        repo_root,
    )

    output = output_dir.expanduser().resolve()
    staging = Path(f"{output}.partial")
    if output.exists():
        raise FileExistsError(f"Final TEST RunBundle exists: {output}")
    if staging.exists():
        raise FileExistsError(f"Partial TEST RunBundle exists: {staging}")

    staging.mkdir(parents=True)
    try:
        manifest = _run_direct(
            repo_root,
            staging,
            config_path,
            authorization,
        )
        staging.rename(output)
        return manifest
    except Exception as exc:
        consumed = (staging / "holdout_consumption.json").is_file()
        write_json(
            staging / "failure.json",
            {
                "phase": "F3.4g-2f",
                "status": "FAIL",
                "exception_type": type(exc).__name__,
                "exception_message": str(exc),
                "holdout_consumed": consumed,
                "same_authorization_rerun_authorized": False,
                "same_holdout_future_reauthorization_possible": not consumed,
                "main_review_required": True,
                "default_next_action": (
                    "REQUIRE_NEW_HELDOUT_VERSION"
                    if consumed
                    else "MAIN_REVIEW_MAY_REAUTHORIZE_SAME_HELDOUT"
                ),
            },
        )
        write_recursive_checksums(staging)
        raise


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--authorization-json", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    manifest = run_controlled_heldout_test(
        REPO_ROOT,
        args.output_dir,
        args.config,
        args.authorization_json,
    )
    print(json.dumps(manifest, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
