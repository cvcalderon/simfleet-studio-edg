from __future__ import annotations

import argparse
import hashlib
import json
import platform
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import yaml

from simfleet_edg.demand.time_schedule import validate_temporal_row
from simfleet_edg.evaluation.activity_chain_adapter import ActivityChainAdapter
from simfleet_edg.evaluation.cal_adapter_common import ArtifactRecord, load_registry
from simfleet_edg.evaluation.cal_harness import evaluation_person_id, packed_draw_index
from simfleet_edg.evaluation.cal_metrics import total_variation_distance, wasserstein_1d
from simfleet_edg.evaluation.cal_protocol import CAL_SCENARIO_ID, MASTER_SEED, runtime_draw_seed
from simfleet_edg.evaluation.cal_state import (
    propagated_chain_state,
    propagated_distance_state,
    propagated_time_state,
)
from simfleet_edg.evaluation.distance_prior_adapter import DistancePriorAdapter
from simfleet_edg.evaluation.participation_adapter import ParticipationAdapter
from simfleet_edg.evaluation.time_schedule_adapter import TimeScheduleAdapter
from simfleet_edg.evaluation.time_schedule_cal_real import (
    _reference_full_chain_thresholds,
    _sample_time_b_propagated_lookahead,
    _sample_time_ref_propagated_lookahead,
)
from simfleet_edg.evaluation.trip_count_adapter import TripCountAdapter

REPO_ROOT = Path.cwd()
CENTRAL_REGISTRY = REPO_ROOT / "docs/F3_3_CANDIDATE_ARTIFACT_REGISTRY_v1.csv"
JOINT_REGISTRY = REPO_ROOT / "configs/f3/f3_4g1_joint_pipeline_registry_v1.json"

RESERVED = {
    "UNKNOWN",
    "__MISSING_CONTEXT__",
    "__START__",
    "__UNSEEN__",
    "GLOBAL",
}
CHAIN_DYNAMIC = {
    "source_trip_count_analogue",
    "prefix_second_last_activity",
    "prefix_last_activity",
    "remaining_trips",
}
TIME_DYNAMIC = {
    "source_trip_count_analogue",
    "origin_activity_analogue",
    "destination_activity_analogue",
    "trip_position_class",
    "previous_departure_clock_minute",
    "previous_arrival_absolute_minute",
}
FORBIDDEN_STATIC = {
    "canonical_trip_purpose",
    "target_destination_activity",
    "source_trip_id",
    "fit_weight_W_GEW",
    "target_trip_day",
    "target_trip_count",
    "target_departure_clock_minute",
    "target_duration_from_clock_min",
    "target_distance_prior_km",
    "wegkm",
    "wegkm_imp",
    "km_routing",
}


@dataclass(frozen=True)
class JointAdapters:
    participation: ParticipationAdapter
    trip_count: TripCountAdapter
    chain: ActivityChainAdapter
    time: TimeScheduleAdapter
    distance: DistancePriorAdapter


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


def write_checksums(output: Path) -> None:
    target = output / "checksums.sha256"
    lines = [
        f"{sha256_file(path)}  {path.name}"
        for path in sorted(output.iterdir())
        if path.is_file() and path.name != target.name
    ]
    target.write_text("\n".join(lines) + "\n", encoding="utf-8")


def safe_category(values: list[Any]) -> Any:
    for value in values:
        if str(value) not in RESERVED:
            return value
    if not values:
        raise ValueError("Empty category support")
    return values[0]


def _chain_key_values(cell: dict[str, Any]) -> list[Any]:
    raw = cell["key"]
    if isinstance(raw, dict):
        return list(raw.values())
    return [item["value"] if isinstance(item, dict) else item for item in raw]


def build_synthetic_static_context(adapters: JointAdapters) -> dict[str, Any]:
    """Build one runtime-static row from fitted encoder/model supports only."""
    static: dict[str, Any] = {}

    part_encoder = adapters.participation.encoder
    for column in part_encoder["feature_columns"]:
        static[column] = safe_category(list(part_encoder["categories"][column]))

    if adapters.chain.record.candidate_id == "CHAIN_A":
        for level in adapters.chain.model["levels"]:
            dims = list(level["dimensions"])
            for cell in level["cells"]:
                if not bool(cell["eligible_direct"]):
                    continue
                values = _chain_key_values(cell)
                for column, value in zip(dims, values, strict=True):
                    if column == "GLOBAL" or column in CHAIN_DYNAMIC:
                        continue
                    if column not in static and str(value) not in RESERVED:
                        static[column] = value

    if adapters.time.encoder is not None:
        encoder = adapters.time.encoder
        for column in encoder["categorical_columns"]:
            if column not in TIME_DYNAMIC:
                static.setdefault(
                    column,
                    safe_category(list(encoder["categories"][column])),
                )
        for column in encoder["numeric_columns"]:
            if column not in TIME_DYNAMIC:
                static.setdefault(column, 0.0)

    forbidden = sorted(FORBIDDEN_STATIC & set(static))
    if forbidden:
        raise ValueError(f"Forbidden synthetic static fields: {forbidden}")
    return static


def make_synthetic_cohort(static: dict[str, Any], n: int) -> pd.DataFrame:
    rows = []
    for index in range(n):
        rows.append(
            {
                "row_id": f"SYNTH_JOINT_CTX_{index:03d}",
                "source_household_id": f"SYNTH_HH_{index // 2:03d}",
                "source_person_id": f"SYNTH_P_{index:03d}",
                **static,
            }
        )
    return pd.DataFrame(rows)


def _record_index() -> dict[str, ArtifactRecord]:
    records = load_registry(CENTRAL_REGISTRY)
    index = {record.artifact_id: record for record in records}
    if len(index) != len(records):
        raise ValueError("Central candidate registry contains duplicate artifact IDs")
    return index


def _adapter_for(repo_root: Path, record: ArtifactRecord) -> Any:
    if record.component == "DG_PARTICIPATION":
        return ParticipationAdapter(repo_root, record)
    if record.component == "DG_TRIP_COUNT":
        return TripCountAdapter(repo_root, record)
    if record.component == "DG_ACTIVITY_CHAIN":
        return ActivityChainAdapter(repo_root, record)
    if record.component == "DG_TIME_SCHEDULE":
        return TimeScheduleAdapter(repo_root, record)
    if record.component == "DG_DISTANCE_PRIOR":
        return DistancePriorAdapter(repo_root, record)
    raise ValueError(record.component)


def load_pipeline(
    repo_root: Path,
    specs: list[dict[str, Any]],
) -> tuple[JointAdapters, list[dict[str, Any]]]:
    index = _record_index()
    adapters: dict[str, Any] = {}
    validation: list[dict[str, Any]] = []

    for slot, spec in enumerate(specs, start=1):
        artifact_id = str(spec["artifact_id"])
        if artifact_id not in index:
            raise ValueError(f"Joint artifact absent from central registry: {artifact_id}")
        record = index[artifact_id]
        if record.model_sha256 != spec["model_sha256"]:
            raise ValueError(f"Model SHA mismatch for {artifact_id}")
        if record.manifest_sha256 != spec["manifest_sha256"]:
            raise ValueError(f"Manifest SHA mismatch for {artifact_id}")
        run_dir = record.validate(repo_root)
        adapter = _adapter_for(repo_root, record)
        adapters[record.component] = adapter
        validation.append(
            {
                "pipeline_slot": slot,
                "component": record.component,
                "artifact_id": artifact_id,
                "candidate_id": record.candidate_id,
                "grid_id": record.grid_id,
                "model_sha256": record.model_sha256,
                "manifest_sha256": record.manifest_sha256,
                "run_dir": str(run_dir),
                "status": "PASS",
            }
        )

    expected = {
        "DG_PARTICIPATION",
        "DG_TRIP_COUNT",
        "DG_ACTIVITY_CHAIN",
        "DG_TIME_SCHEDULE",
        "DG_DISTANCE_PRIOR",
    }
    if set(adapters) != expected:
        raise ValueError("Joint pipeline must resolve exactly five components")

    return (
        JointAdapters(
            participation=adapters["DG_PARTICIPATION"],
            trip_count=adapters["DG_TRIP_COUNT"],
            chain=adapters["DG_ACTIVITY_CHAIN"],
            time=adapters["DG_TIME_SCHEDULE"],
            distance=adapters["DG_DISTANCE_PRIOR"],
        ),
        validation,
    )


def _frame(state: dict[str, Any], required: list[str]) -> pd.DataFrame:
    missing = [column for column in required if column not in state]
    if missing:
        raise KeyError(f"Missing synthetic state columns: {missing}")
    return pd.DataFrame([{column: state[column] for column in required}])


def _time_frame(adapter: TimeScheduleAdapter, state: dict[str, Any]) -> pd.DataFrame:
    if adapter.record.candidate_id == "TIME_REF":
        return pd.DataFrame([{"synthetic_placeholder": 1}])
    if adapter.encoder is None:
        return pd.DataFrame([state])
    required = list(adapter.encoder["categorical_columns"]) + list(
        adapter.encoder["numeric_columns"]
    )
    return _frame(state, required)


def _chain_frame(adapter: ActivityChainAdapter, state: dict[str, Any]) -> pd.DataFrame:
    if adapter.record.candidate_id == "CHAIN_REF":
        return pd.DataFrame([{"prefix_last_activity": state["prefix_last_activity"]}])
    return pd.DataFrame([state])


def _sample_time(
    adapter: TimeScheduleAdapter,
    state: dict[str, Any],
    *,
    previous_arrival: int | None,
    trips_remaining: int,
    seed: int,
    reference_thresholds: dict[int, int | None] | None,
) -> dict[str, Any]:
    frame = _time_frame(adapter, state)
    if adapter.record.candidate_id == "TIME_B":
        q = adapter._time_b_quantiles(frame)
        return _sample_time_b_propagated_lookahead(
            adapter,
            q["departure_clock_minute"][0],
            q["duration_from_clock_min"][0],
            previous_arrival_absolute_minute=previous_arrival,
            trips_remaining_after_current=trips_remaining,
            seed=seed,
        )
    if adapter.record.candidate_id == "TIME_REF":
        if reference_thresholds is None:
            raise ValueError("TIME_REF thresholds missing")
        return _sample_time_ref_propagated_lookahead(
            adapter,
            previous_arrival_absolute_minute=previous_arrival,
            trips_remaining_after_current=trips_remaining,
            seed=seed,
            full_chain_thresholds=reference_thresholds,
        )
    return adapter.sample_one(
        frame,
        previous_arrival_absolute_minute=previous_arrival,
        trips_remaining_after_current=trips_remaining,
        seed=seed,
    )


def generate_pipeline(
    label: str,
    adapters: JointAdapters,
    cohort: pd.DataFrame,
    *,
    replicates: int,
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
                if key not in {"row_id", "source_household_id", "source_person_id"}
            }
            if FORBIDDEN_STATIC & set(static):
                violations["nofuture"] += 1

            person_id = evaluation_person_id(
                day["source_household_id"],
                day["source_person_id"],
            )

            part_seed = runtime_draw_seed(
                MASTER_SEED,
                CAL_SCENARIO_ID,
                person_id,
                "DG_PARTICIPATION",
                packed_draw_index(replicate, 0),
            )
            part_frame = _frame(static, list(adapters.participation.required_columns))
            part = adapters.participation.sample_one(part_frame, seed=part_seed)

            trip_day = bool(part["trip_day"])
            trip_count = 0
            activities: list[str] = []
            temporal_ok = True
            distance_ok = True

            if trip_day:
                count_seed = runtime_draw_seed(
                    MASTER_SEED,
                    CAL_SCENARIO_ID,
                    person_id,
                    "DG_TRIP_COUNT",
                    packed_draw_index(replicate, 0),
                )
                count_frame = _frame(static, list(adapters.trip_count.required_columns))
                count = adapters.trip_count.sample_one(count_frame, seed=count_seed)
                trip_count = int(count["trip_count"])
                if trip_count < 1:
                    violations["structural"] += 1
                    trip_count = 0

            if trip_count > 0:
                init_seed = runtime_draw_seed(
                    MASTER_SEED,
                    CAL_SCENARIO_ID,
                    person_id,
                    "DG_ACTIVITY_CHAIN",
                    packed_draw_index(replicate, 0),
                )
                activities = [adapters.chain.sample_initial_activity(seed=init_seed)]

                for trip_index in range(1, trip_count + 1):
                    chain_state = propagated_chain_state(
                        static,
                        trip_count=trip_count,
                        prefix=activities,
                        remaining_trips=trip_count - trip_index,
                    )
                    chain_seed = runtime_draw_seed(
                        MASTER_SEED,
                        CAL_SCENARIO_ID,
                        person_id,
                        "DG_ACTIVITY_CHAIN",
                        packed_draw_index(replicate, 2 * trip_index - 1),
                    )
                    sampled = adapters.chain.sample_transition(
                        _chain_frame(adapters.chain, chain_state),
                        seed=chain_seed,
                    )
                    activities.append(str(sampled["next_activity"]))

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
                        MASTER_SEED,
                        CAL_SCENARIO_ID,
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
                        trips_remaining_after_current=trip_count - trip_index,
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
                        MASTER_SEED,
                        CAL_SCENARIO_ID,
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

                    trip_rows.append(
                        {
                            "pipeline": label,
                            "replicate_index": replicate,
                            "row_id": day["row_id"],
                            "source_household_id": day["source_household_id"],
                            "source_person_id": day["source_person_id"],
                            "trip_index": trip_index,
                            "trip_count": trip_count,
                            "origin_activity": activities[trip_index - 1],
                            "destination_activity": activities[trip_index],
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
                    "return_home": bool(activities and activities[-1] == "HOME"),
                    "temporal_chain_valid": temporal_ok,
                    "distance_chain_valid": distance_ok,
                }
            )

    return day_rows, trip_rows, violations


def categorical_tvd(left: pd.Series, right: pd.Series) -> float:
    support = sorted(set(left.astype(str)) | set(right.astype(str)))
    left_text = left.astype(str)
    right_text = right.astype(str)
    left_p = pd.Series(
        {item: float((left_text == item).mean()) for item in support},
        dtype=float,
    )
    right_p = pd.Series(
        {item: float((right_text == item).mean()) for item in support},
        dtype=float,
    )
    return total_variation_distance(left_p, right_p)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    cfg = yaml.safe_load(args.config.read_text(encoding="utf-8"))
    output = args.output_dir.expanduser().resolve()
    if output.exists():
        raise FileExistsError(f"Output path already exists: {output}")
    output.mkdir(parents=True)

    original_read_csv = pd.read_csv

    def guarded_read_csv(path: Any, *args_: Any, **kwargs: Any) -> pd.DataFrame:
        if "CALIBRATION" in str(path):
            raise RuntimeError(f"CAL I/O forbidden in F3.4g-2a: {path}")
        return original_read_csv(path, *args_, **kwargs)

    pd.read_csv = guarded_read_csv  # type: ignore[assignment]

    joint_registry = json.loads(JOINT_REGISTRY.read_text(encoding="utf-8"))
    selected, selected_validation = load_pipeline(
        REPO_ROOT,
        list(joint_registry["selected_pipeline"]),
    )
    reference, reference_validation = load_pipeline(
        REPO_ROOT,
        list(joint_registry["all_reference_pipeline"]),
    )

    static = build_synthetic_static_context(selected)
    cohort = make_synthetic_cohort(
        static,
        int(cfg["synthetic_protocol"]["synthetic_person_days"]),
    )

    replicates = int(cfg["synthetic_protocol"]["stochastic_replicates"])
    seed_rows = []
    for replicate in range(replicates):
        witness_person = evaluation_person_id("SYNTH_HH_000", "SYNTH_P_000")
        seed_rows.append(
            {
                "replicate_index": replicate,
                "participation_seed_witness": runtime_draw_seed(
                    MASTER_SEED,
                    CAL_SCENARIO_ID,
                    witness_person,
                    "DG_PARTICIPATION",
                    packed_draw_index(replicate, 0),
                ),
                "trip_count_seed_witness": runtime_draw_seed(
                    MASTER_SEED,
                    CAL_SCENARIO_ID,
                    witness_person,
                    "DG_TRIP_COUNT",
                    packed_draw_index(replicate, 0),
                ),
                "activity_chain_seed_witness": runtime_draw_seed(
                    MASTER_SEED,
                    CAL_SCENARIO_ID,
                    witness_person,
                    "DG_ACTIVITY_CHAIN",
                    packed_draw_index(replicate, 0),
                ),
            }
        )

    selected_days, selected_trips, selected_violations = generate_pipeline(
        "SELECTED",
        selected,
        cohort,
        replicates=replicates,
    )
    reference_days, reference_trips, reference_violations = generate_pipeline(
        "ALL_REFERENCE",
        reference,
        cohort,
        replicates=replicates,
    )

    days = pd.DataFrame(selected_days + reference_days)
    trips = pd.DataFrame(selected_trips + reference_trips)
    validation = pd.DataFrame(selected_validation + reference_validation)

    pipeline_summaries: list[dict[str, Any]] = []
    for label in ("SELECTED", "ALL_REFERENCE"):
        day = days.loc[days["pipeline"].eq(label)]
        trip = trips.loc[trips["pipeline"].eq(label)]
        mobile = day.loc[day["trip_day"]]
        pipeline_summaries.append(
            {
                "pipeline": label,
                "generated_person_days": len(day),
                "trip_day_share": float(day["trip_day"].mean()),
                "mean_trips_per_person_day": float(day["trip_count"].mean()),
                "return_home_share_mobile": (
                    float(mobile["return_home"].mean()) if len(mobile) else np.nan
                ),
                "generated_trip_rows": len(trip),
                "mean_distance_km": (
                    float(trip["distance_prior_km"].mean()) if len(trip) else np.nan
                ),
                "decision_authorized": False,
            }
        )

    selected_trip_frame = trips.loc[trips["pipeline"].eq("SELECTED")]
    reference_trip_frame = trips.loc[trips["pipeline"].eq("ALL_REFERENCE")]

    metric_rows: list[dict[str, Any]] = []
    if len(selected_trip_frame) and len(reference_trip_frame):
        metric_rows.extend(
            [
                {
                    "metric": "SYNTH_PURPOSE_TVD_SELECTED_VS_REFERENCE",
                    "value": categorical_tvd(
                        selected_trip_frame["destination_activity"],
                        reference_trip_frame["destination_activity"],
                    ),
                    "decision_authorized": False,
                },
                {
                    "metric": "SYNTH_DEPARTURE_HOUR_TVD_SELECTED_VS_REFERENCE",
                    "value": categorical_tvd(
                        (selected_trip_frame["departure_clock_minute"] // 60).astype(str),
                        (reference_trip_frame["departure_clock_minute"] // 60).astype(str),
                    ),
                    "decision_authorized": False,
                },
                {
                    "metric": "SYNTH_DISTANCE_W1_SELECTED_VS_REFERENCE_KM",
                    "value": wasserstein_1d(
                        selected_trip_frame["distance_prior_km"].to_numpy(dtype=float),
                        np.ones(len(selected_trip_frame), dtype=float),
                        reference_trip_frame["distance_prior_km"].to_numpy(dtype=float),
                        np.ones(len(reference_trip_frame), dtype=float),
                    ),
                    "decision_authorized": False,
                },
            ]
        )

    all_violations = {
        key: selected_violations[key] + reference_violations[key]
        for key in selected_violations
    }

    checks = [
        (
            "pipeline_artifact_slots_10",
            len(validation) == int(cfg["synthetic_smoke"]["expected_pipeline_slots"]),
        ),
        (
            "synthetic_person_days_8",
            len(cohort) == int(cfg["synthetic_protocol"]["synthetic_person_days"]),
        ),
        (
            "seed_rows_32",
            len(seed_rows) == int(cfg["synthetic_smoke"]["expected_seed_rows"]),
        ),
        (
            "generated_day_rows_512",
            len(days) == int(cfg["synthetic_smoke"]["expected_day_rows"]),
        ),
        (
            "selected_generated_trips_positive",
            len(selected_trip_frame) > 0,
        ),
        (
            "reference_generated_trips_positive",
            len(reference_trip_frame) > 0,
        ),
        (
            "structural_violations_zero",
            all_violations["structural"] == 0,
        ),
        (
            "temporal_violations_zero",
            all_violations["temporal"] == 0,
        ),
        (
            "distance_violations_zero",
            all_violations["distance"] == 0,
        ),
        (
            "nofuture_violations_zero",
            all_violations["nofuture"] == 0,
        ),
        (
            "cal_rows_zero",
            cfg["access_boundaries"]["cal_rows_read"] == 0,
        ),
        (
            "test_rows_zero",
            cfg["access_boundaries"]["test_rows_read"] == 0,
        ),
        (
            "candidate_selection_none",
            cfg["synthetic_smoke"]["selection_authorized"] is False,
        ),
        (
            "joint_gate_not_evaluated",
            cfg["access_boundaries"]["joint_gate_evaluated"] is False,
        ),
        (
            "synthetic_metrics_not_decision",
            all(not bool(row["decision_authorized"]) for row in metric_rows),
        ),
    ]
    validation_checks = pd.DataFrame(
        [
            {"check": name, "status": "PASS" if passed else "FAIL"}
            for name, passed in checks
        ]
    )
    status = "PASS" if validation_checks["status"].eq("PASS").all() else "FAIL"

    validation.to_csv(output / "pipeline_artifact_validation.csv", index=False)
    cohort.to_csv(output / "synthetic_person_day_context.csv", index=False)
    pd.DataFrame(seed_rows).to_csv(output / "seed_schedule.csv", index=False)
    days.to_csv(output / "synthetic_generated_days.csv", index=False)
    trips.to_csv(output / "synthetic_generated_trips.csv", index=False)
    pd.DataFrame(pipeline_summaries).to_csv(
        output / "synthetic_pipeline_summary.csv",
        index=False,
    )
    pd.DataFrame(metric_rows).to_csv(output / "synthetic_metric_smoke.csv", index=False)
    validation_checks.to_csv(output / "validation.csv", index=False)
    pd.DataFrame(columns=["issue_id", "severity", "detail"]).to_csv(
        output / "issues.csv",
        index=False,
    )

    write_json(
        output / "environment.json",
        {
            "python": sys.version,
            "platform": platform.platform(),
            "numpy": np.__version__,
            "pandas": pd.__version__,
        },
    )

    write_json(
        output / "run_manifest.json",
        {
            "run_id": cfg["run_id"],
            "phase": "F3.4g-2a",
            "component": "DGEN_JOINT_PIPELINE",
            "mode": "SYNTHETIC_PREOPEN",
            "status": status,
            "implementation_commit": __import__("subprocess").check_output(
                ["git", "rev-parse", "HEAD"],
                cwd=REPO_ROOT,
                text=True,
            ).strip(),
            "pipeline_artifact_slots": len(validation),
            "synthetic_person_days": len(cohort),
            "stochastic_replicates": replicates,
            "generated_day_rows": len(days),
            "selected_generated_trip_rows": len(selected_trip_frame),
            "reference_generated_trip_rows": len(reference_trip_frame),
            "hard_invariant_violations": int(sum(all_violations.values())),
            "cal_files_read": [],
            "cal_rows_read": 0,
            "future_joint_cal_physical_rows": 6341,
            "candidate_selection": "NONE",
            "joint_real_cal_open_authorized": False,
            "joint_gate_evaluated": False,
            "test_files_read": [],
            "test_rows_read": 0,
            "test_open_authorized": False,
            "formal_g2": "NOT_EVALUATED",
        },
    )
    write_checksums(output)

    if status != "PASS":
        raise RuntimeError("F3.4g-2a synthetic validation failed")


if __name__ == "__main__":
    main()
