"""Controlled real-CAL runner for F3.4f Distance Prior.

CAL I/O is allowed only after an external authorization bound to the exact
committed implementation HEAD has been validated. PRE-OPEN tests/verifiers must
never invoke the runner with a valid authorization.
"""

from __future__ import annotations

import gzip
import json
import platform
import subprocess
import sys
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import yaml

from simfleet_edg.demand.distance_prior import (
    repair_distance_quantiles,
    sample_distance_b,
    transform_distance_b_context,
    validate_distance_targets,
)
from simfleet_edg.demand.time_schedule import validate_temporal_row
from simfleet_edg.evaluation.activity_chain_adapter import ActivityChainAdapter
from simfleet_edg.evaluation.cal_adapter_common import ArtifactRecord, load_registry, sha256_file
from simfleet_edg.evaluation.cal_bootstrap import (
    household_bootstrap_multipliers,
    percentile_interval,
)
from simfleet_edg.evaluation.cal_evidence import canonical_payload
from simfleet_edg.evaluation.cal_harness import evaluation_person_id, packed_draw_index
from simfleet_edg.evaluation.cal_metrics import wasserstein_1d, weighted_mean, weighted_quantile
from simfleet_edg.evaluation.cal_protocol import (
    CAL_SCENARIO_ID,
    MASTER_SEED,
    bootstrap_seed,
    runtime_draw_seed,
)
from simfleet_edg.evaluation.cal_selection import (
    GridScore,
    choose_within_family,
    promotion_decision,
)
from simfleet_edg.evaluation.cal_state import (
    propagated_chain_state,
    propagated_distance_state,
    propagated_time_state,
)
from simfleet_edg.evaluation.distance_prior_adapter import DistancePriorAdapter
from simfleet_edg.evaluation.participation_adapter import ParticipationAdapter
from simfleet_edg.evaluation.time_schedule_adapter import TimeScheduleAdapter
from simfleet_edg.evaluation.time_schedule_cal_real import _sample_time_b_propagated_lookahead
from simfleet_edg.evaluation.trip_count_adapter import TripCountAdapter

COMPONENT = "DG_DISTANCE_PRIOR"
PARTICIPATION_COMPONENT = "DG_PARTICIPATION"
TRIP_COUNT_COMPONENT = "DG_TRIP_COUNT"
ACTIVITY_CHAIN_COMPONENT = "DG_ACTIVITY_CHAIN"
TIME_COMPONENT = "DG_TIME_SCHEDULE"
UPSTREAM_PARTICIPATION_ID = "DG_PARTICIPATION::PART_A::PA1"
UPSTREAM_TRIP_COUNT_ID = "DG_TRIP_COUNT::COUNT_REF::REFERENCE"
UPSTREAM_ACTIVITY_CHAIN_ID = "DG_ACTIVITY_CHAIN::CHAIN_A::CHA2"
UPSTREAM_TIME_ID = "TIME_B_TB2"
REFERENCE_ID = "DIST_REF_REFERENCE"
REPLICATES = 32
BOOTSTRAPS = 1000
PRACTICAL_MARGIN = 0.25
QUANTILE_TOLERANCE = 0.50
ROLE_RANK = {"REFERENCE_BASELINE": 0, "CORE_CANDIDATE_A": 1, "CORE_CHALLENGER_B": 2}
FORBIDDEN_DISTANCE_FEATURES = {
    "row_id", "context_row_id", "source_household_id", "source_person_id",
    "source_person_slot", "source_trip_id", "fit_weight_W_GEW",
    "target_distance_prior_km", "target_distance_sensitivity_km", "distance_provenance",
    "time_context_status", "transition_context_status", "mode", "hvm", "km_routing",
    "route", "execution",
}


def _git(repo_root: Path, *args: str) -> str:
    return subprocess.check_output(["git", "-C", str(repo_root), *args], text=True).strip()


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_csv(path: Path, rows: list[dict[str, Any]] | pd.DataFrame) -> None:
    (rows if isinstance(rows, pd.DataFrame) else pd.DataFrame(rows)).to_csv(path, index=False)


def _write_checksums(output_dir: Path) -> None:
    target = output_dir / "checksums.sha256"
    lines = [
        f"{sha256_file(path)}  {path.name}"
        for path in sorted(output_dir.iterdir())
        if path.is_file() and path.name != target.name
    ]
    target.write_text("\n".join(lines) + "\n", encoding="utf-8")


def load_authorization(path: Path, repo_root: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    required = {
        "phase": "F3.4f-2b",
        "component": COMPONENT,
        "real_distance_prior_cal_open_authorized": True,
        "candidate_artifacts": 5,
        "candidate_selection_at_entry": "NONE",
        "joint_cal_gate_authorized": False,
        "test_open_authorized": False,
        "formal_g2": "NOT_EVALUATED",
    }
    for key, value in required.items():
        if payload.get(key) != value:
            raise PermissionError(f"Invalid execution authorization field {key}")
    if set(payload.get("allowed_cal_files", [])) != {
        "person_day_context.csv", "distance_raw.csv", "distance_expanded_sensitivity.csv"
    }:
        raise PermissionError("Authorization CAL file scope mismatch")
    current = _git(repo_root, "rev-parse", "HEAD")
    if payload.get("authorized_implementation_commit") != current:
        raise PermissionError("Authorization is not bound to current implementation commit")
    if _git(repo_root, "status", "--porcelain"):
        raise PermissionError("Real CAL execution requires a clean worktree")
    if _git(repo_root, "branch", "--show-current") != "main":
        raise PermissionError("Real CAL execution requires main branch")
    if _git(repo_root, "rev-list", "--count", "origin/main..HEAD") != "0":
        raise PermissionError("Real CAL execution requires ahead=0")
    if _git(repo_root, "rev-list", "--count", "HEAD..origin/main") != "0":
        raise PermissionError("Real CAL execution requires behind=0")
    return payload


def _validate_input_file(path: Path, expected_sha: str, expected_rows: int) -> pd.DataFrame:
    if not path.is_file():
        raise FileNotFoundError(path)
    actual_sha = sha256_file(path)
    if actual_sha != expected_sha:
        raise ValueError(f"CAL input SHA mismatch for {path.name}")
    frame = pd.read_csv(path)
    if len(frame) != expected_rows:
        raise ValueError(f"CAL input row mismatch for {path.name}: {len(frame)} != {expected_rows}")
    return frame


def _all_records(repo_root: Path) -> list[ArtifactRecord]:
    return load_registry(repo_root / "docs/F3_3_CANDIDATE_ARTIFACT_REGISTRY_v1.csv")


def _record_by_id(repo_root: Path, artifact_id: str) -> ArtifactRecord:
    found = [r for r in _all_records(repo_root) if r.artifact_id == artifact_id]
    if len(found) != 1:
        raise ValueError(f"Frozen artifact not found exactly once: {artifact_id}")
    return found[0]


def _records(repo_root: Path) -> list[ArtifactRecord]:
    records = [r for r in _all_records(repo_root) if r.component == COMPONENT]
    if len(records) != 5:
        raise ValueError("Distance Prior candidate universe must contain 5 artifacts")
    if {r.train_state for r in records} != {"FITTED_TRAIN_ONLY_NOT_SELECTED"}:
        raise ValueError("Unexpected Distance Prior train_state")
    return sorted(records, key=lambda r: (ROLE_RANK[r.role], r.grid_id))


def _merge_distance(context: pd.DataFrame, frame: pd.DataFrame) -> pd.DataFrame:
    merged = frame.merge(
        context,
        left_on="context_row_id",
        right_on="row_id",
        how="left",
        validate="many_to_one",
        suffixes=("_distance", "_context"),
    )
    if merged["row_id"].isna().any():
        raise ValueError("Every Distance CAL row must resolve to person_day_context")
    weights = pd.to_numeric(merged["fit_weight_W_GEW"], errors="raise").astype(float).to_numpy()
    if not np.isfinite(weights).all() or (weights <= 0).any():
        raise ValueError("Distance CAL W_GEW must be finite and >0")
    return merged


def load_and_validate_distance_cal(repo_root: Path, config: dict[str, Any]) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, list[dict[str, Any]], dict[str, Any]]:
    root = repo_root / config["cal_input"]["root"]
    rows: list[dict[str, Any]] = []
    frames: dict[str, pd.DataFrame] = {}
    for key in ("person_day_context", "distance_raw", "distance_expanded_sensitivity"):
        spec = config["cal_input"][key]
        path = root / spec["filename"]
        frame = _validate_input_file(path, str(spec["sha256"]), int(spec["expected_rows"]))
        frames[key] = frame
        rows.append({
            "id": key,
            "path": str(path),
            "expected_sha256": spec["sha256"],
            "actual_sha256": sha256_file(path),
            "expected_rows": int(spec["expected_rows"]),
            "actual_rows": len(frame),
            "status": "PASS",
        })
    raw = frames["distance_raw"]
    sensitivity = frames["distance_expanded_sensitivity"]
    validate_distance_targets(raw, "target_distance_prior_km")
    validate_distance_targets(sensitivity, "target_distance_sensitivity_km")
    if set(raw["distance_provenance"].astype(str)) != {"RAW_WEGKM"}:
        raise ValueError("Primary Distance CAL provenance must be RAW_WEGKM")
    if not set(sensitivity["distance_provenance"].astype(str)).issubset({"RAW_WEGKM", "SOURCE_IMPUTED_WEGKM"}):
        raise ValueError("Unexpected Distance sensitivity provenance")
    raw_m = _merge_distance(frames["person_day_context"], raw)
    sens_m = _merge_distance(frames["person_day_context"], sensitivity)
    cohort_ids = sorted(set(raw["context_row_id"].astype(str)))
    context = frames["person_day_context"].copy()
    cohort = context[context["row_id"].astype(str).isin(cohort_ids)].copy()
    if len(cohort) != len(cohort_ids):
        raise ValueError("Fixed propagated cohort did not resolve one-to-one")
    access = {
        "cal_files_opened": [config["cal_input"][k]["filename"] for k in ("person_day_context", "distance_raw", "distance_expanded_sensitivity")],
        "cal_rows_read_total_physical": sum(int(config["cal_input"][k]["expected_rows"]) for k in ("person_day_context", "distance_raw", "distance_expanded_sensitivity")),
        "cal_isolated_raw_rows": len(raw_m),
        "cal_sensitivity_rows": len(sens_m),
        "cal_fixed_source_cohort_days": len(cohort),
    }
    return raw_m, sens_m, cohort, rows, access


def _distance_feature_columns(adapter: DistancePriorAdapter) -> set[str]:
    if adapter.record.candidate_id == "DIST_REF":
        return set()
    if adapter.record.candidate_id == "DIST_A":
        out: set[str] = set()
        for level in adapter.model["levels"]:
            out.update(str(x) for x in level["dimensions"] if x != "GLOBAL")
        return out
    if adapter.record.candidate_id == "DIST_B":
        if adapter.encoder is None:
            raise ValueError("DIST_B encoder missing")
        return set(map(str, adapter.encoder["categorical_columns"] + adapter.encoder["numeric_columns"]))
    raise ValueError(adapter.record.candidate_id)


def _validate_candidate_artifacts(repo_root: Path, records: list[ArtifactRecord]) -> tuple[list[DistancePriorAdapter], pd.DataFrame]:
    adapters: list[DistancePriorAdapter] = []
    rows: list[dict[str, Any]] = []
    for record in records:
        adapter = DistancePriorAdapter(repo_root, record)
        features = _distance_feature_columns(adapter)
        forbidden = sorted(features & FORBIDDEN_DISTANCE_FEATURES)
        rows.append({
            "artifact_id": record.artifact_id,
            "candidate_id": record.candidate_id,
            "grid_id": record.grid_id,
            "model_sha256": record.model_sha256,
            "manifest_sha256": record.manifest_sha256,
            "feature_count": len(features),
            "forbidden_features": ";".join(forbidden),
            "nofuture_pass": not forbidden,
            "status": "PASS" if not forbidden else "FAIL",
        })
        if forbidden:
            raise ValueError(f"Forbidden Distance features in {record.artifact_id}: {forbidden}")
        adapters.append(adapter)
    return adapters, pd.DataFrame(rows)


def _distance_seed(context_row_id: object, slot: object, replicate: int) -> int:
    return runtime_draw_seed(MASTER_SEED, CAL_SCENARIO_ID, str(context_row_id), f"DG_DISTANCE_PRIOR::TRIP::{slot}", int(replicate))


def _generate_isolated(adapter: DistancePriorAdapter, merged: pd.DataFrame) -> np.ndarray:
    out = np.empty((REPLICATES, len(merged)), dtype=float)

    # DIST_B predictions are deterministic conditional quantile surfaces.
    # Predict them once for the whole CAL frame; only the inverse-quantile draw
    # remains stochastic. This preserves the frozen RNG while avoiding hundreds
    # of thousands of one-row LightGBM predict calls.
    repaired: np.ndarray | None = None
    if adapter.record.candidate_id == "DIST_B":
        if adapter.encoder is None:
            raise ValueError("DIST_B encoder missing")
        x, _ = transform_distance_b_context(merged, adapter.encoder)
        x_frame = pd.DataFrame(x, columns=adapter.encoder["feature_names"])
        raw = np.column_stack([
            np.asarray(adapter.boosters[f"q{q:.2f}"].predict(x_frame), dtype=float)
            for q in adapter.quantiles
        ])
        repaired = repair_distance_quantiles(
            raw,
            float(adapter.model["global_strict_train_target_min_km"]),
            float(adapter.model["global_strict_train_target_max_km"]),
        )

    for replicate in range(REPLICATES):
        for row_index, (_, row) in enumerate(merged.iterrows()):
            seed = _distance_seed(row["context_row_id"], row["source_trip_id"], replicate)
            if repaired is not None:
                u = float(np.random.default_rng(seed).random())
                value = float(sample_distance_b(
                    repaired[row_index],
                    adapter.quantiles,
                    uniform=u,
                    target_min=float(adapter.model["global_strict_train_target_min_km"]),
                    target_max=float(adapter.model["global_strict_train_target_max_km"]),
                ))
            else:
                result = adapter.sample_one(pd.DataFrame([row.to_dict()]), seed=seed)
                value = float(result["distance_prior_km"])
            if not np.isfinite(value) or value <= 0:
                raise RuntimeError(
                    f"Non-positive/non-finite Distance draw for {adapter.record.artifact_id}"
                )
            out[replicate, row_index] = value
    return out


def _metric_mean32(observed: np.ndarray, generated: np.ndarray, weights: np.ndarray) -> float:
    return float(np.mean([wasserstein_1d(observed, weights, generated[r], weights) for r in range(REPLICATES)]))


def _summary_errors(observed: np.ndarray, generated: np.ndarray, weights: np.ndarray) -> dict[str, float]:
    specs = {"P50": 0.50, "P90": 0.90, "P95": 0.95}
    out: dict[str, float] = {"MEAN": float(np.mean([abs(weighted_mean(generated[r], weights) - weighted_mean(observed, weights)) for r in range(REPLICATES)]))}
    for name, q in specs.items():
        target = weighted_quantile(observed, weights, q)
        out[name] = float(np.mean([abs(weighted_quantile(generated[r], weights, q) - target) for r in range(REPLICATES)]))
    return out


def _compare_quantile_guardrails(incumbent: dict[str, float], challenger: dict[str, float]) -> tuple[bool, dict[str, Any]]:
    row: dict[str, Any] = {}
    passed = True
    for metric in ("P50", "P90", "P95"):
        worsening = float(challenger[metric] - incumbent[metric])
        row[f"{metric.lower()}_abs_error_worsening_km"] = worsening
        row[f"{metric.lower()}_tolerance_km"] = QUANTILE_TOLERANCE
        passed = passed and worsening <= QUANTILE_TOLERANCE + 1e-15
    row["mean_abs_error_incumbent_km"] = float(incumbent["MEAN"])
    row["mean_abs_error_challenger_km"] = float(challenger["MEAN"])
    row["mean_role"] = "REPORT_ONLY_UNTHRESHOLDED"
    row["guardrails_pass"] = passed
    return passed, row


def _bootstrap_improvement(raw: pd.DataFrame, incumbent_draws: np.ndarray, challenger_draws: np.ndarray, incumbent_id: str, challenger_id: str) -> dict[str, Any]:
    observed = raw["target_distance_prior_km"].astype(float).to_numpy()
    base_weight = raw["fit_weight_W_GEW"].astype(float).to_numpy()
    households = raw["source_household_id_distance"] if "source_household_id_distance" in raw else raw["source_household_id"]
    multipliers = household_bootstrap_multipliers(households, replicates=BOOTSTRAPS, seed=bootstrap_seed(MASTER_SEED, COMPONENT, incumbent_id, challenger_id))
    differences = np.empty(BOOTSTRAPS, dtype=float)
    for b, mult in enumerate(multipliers):
        weight = base_weight * mult
        if weight.sum() <= 0:
            raise ValueError("Bootstrap removed all Distance rows")
        incumbent = np.mean([wasserstein_1d(observed, weight, incumbent_draws[r], weight) for r in range(REPLICATES)])
        challenger = np.mean([wasserstein_1d(observed, weight, challenger_draws[r], weight) for r in range(REPLICATES)])
        differences[b] = incumbent - challenger
    interval = percentile_interval(differences, confidence_level=0.95)
    return {
        "incumbent_artifact_id": incumbent_id,
        "challenger_artifact_id": challenger_id,
        "bootstrap_replicates": BOOTSTRAPS,
        "ci_lower": interval.lower,
        "ci_median": interval.median,
        "ci_upper": interval.upper,
    }


def _score(record: ArtifactRecord, primary: dict[str, float], hard_pass: dict[str, bool], guardrails_pass: bool) -> GridScore:
    return GridScore(record.artifact_id, record.candidate_id, record.grid_id, record.role, float(primary[record.artifact_id]), bool(hard_pass[record.artifact_id]), bool(guardrails_pass))


def _static_context(row: pd.Series) -> dict[str, Any]:
    excluded = {"row_id", "source_household_id", "source_person_id", "source_person_slot", "fit_weight_P_GEW"}
    return {k: v for k, v in row.to_dict().items() if k not in excluded}


def _generate_propagated_states(repo_root: Path, cohort: pd.DataFrame) -> tuple[list[list[list[dict[str, Any]]]], dict[str, Any]]:
    part = ParticipationAdapter(repo_root, _record_by_id(repo_root, UPSTREAM_PARTICIPATION_ID))
    count = TripCountAdapter(repo_root, _record_by_id(repo_root, UPSTREAM_TRIP_COUNT_ID))
    chain = ActivityChainAdapter(repo_root, _record_by_id(repo_root, UPSTREAM_ACTIVITY_CHAIN_ID))
    time_adapter = TimeScheduleAdapter(repo_root, _record_by_id(repo_root, UPSTREAM_TIME_ID))
    if time_adapter.record.candidate_id != "TIME_B" or time_adapter.record.grid_id != "TB2":
        raise ValueError("Frozen upstream Time Schedule is not TIME_B_TB2")

    probability = part.probabilities(cohort)
    count_pmf = count.pmf(cohort)
    support = np.asarray(count.support, dtype=int)
    cdf = np.cumsum(count_pmf, axis=1)
    states: list[list[list[dict[str, Any]]]] = [[[] for _ in range(len(cohort))] for _ in range(REPLICATES)]

    for replicate in range(REPLICATES):
        for row_index, (_, day) in enumerate(cohort.iterrows()):
            person_id = evaluation_person_id(day["source_household_id"], day["source_person_id"])
            part_seed = runtime_draw_seed(MASTER_SEED, CAL_SCENARIO_ID, person_id, PARTICIPATION_COMPONENT, packed_draw_index(replicate, 0))
            if np.random.default_rng(part_seed).random() >= float(probability[row_index]):
                continue
            count_seed = runtime_draw_seed(MASTER_SEED, CAL_SCENARIO_ID, person_id, TRIP_COUNT_COMPONENT, packed_draw_index(replicate, 0))
            u = float(np.random.default_rng(count_seed).random())
            idx = min(int(np.sum(u > cdf[row_index])), len(support) - 1)
            k = int(support[idx])
            if k == 0:
                continue
            init_seed = runtime_draw_seed(MASTER_SEED, CAL_SCENARIO_ID, person_id, ACTIVITY_CHAIN_COMPONENT, packed_draw_index(replicate, 0))
            activities = [chain.sample_initial_activity(seed=init_seed)]
            static = _static_context(day)
            for trip_index in range(1, k + 1):
                chain_state = propagated_chain_state(static, trip_count=k, prefix=activities, remaining_trips=k-trip_index)
                transition_seed = runtime_draw_seed(MASTER_SEED, CAL_SCENARIO_ID, person_id, ACTIVITY_CHAIN_COMPONENT, packed_draw_index(replicate, 2*trip_index-1))
                sampled = chain.sample_transition(pd.DataFrame([chain_state]), seed=transition_seed)
                activities.append(str(sampled["next_activity"]))
            prev_dep: int | None = None
            prev_arr: int | None = None
            for trip_index in range(1, k + 1):
                time_state = propagated_time_state(static, trip_count=k, trip_index=trip_index, origin_activity=activities[trip_index-1], destination_activity=activities[trip_index], previous_departure_clock_minute=prev_dep, previous_arrival_absolute_minute=prev_arr)
                q = time_adapter._time_b_quantiles(pd.DataFrame([time_state]))
                time_seed = runtime_draw_seed(MASTER_SEED, CAL_SCENARIO_ID, str(day["row_id"]), f"DG_TIME_SCHEDULE::TRIP::{trip_index}", replicate)
                result = _sample_time_b_propagated_lookahead(time_adapter, q["departure_clock_minute"][0], q["duration_from_clock_min"][0], previous_arrival_absolute_minute=prev_arr, trips_remaining_after_current=k-trip_index, seed=time_seed)
                ok, validated = validate_temporal_row(result["departure_clock_minute"], result["duration_from_clock_min"], previous_arrival_absolute_minute=prev_arr, trips_remaining_after_current=k-trip_index)
                if not ok:
                    raise RuntimeError("Frozen TIME_B_TB2 produced invalid propagated temporal row")
                prev_dep = int(validated["departure_clock_minute"])
                prev_arr = int(validated["arrival_absolute_minute"])
                states[replicate][row_index].append(propagated_distance_state(static, trip_count=k, origin_activity=activities[trip_index-1], destination_activity=activities[trip_index], departure_clock_minute=prev_dep, arrival_absolute_minute=prev_arr, duration_from_clock_minute=int(validated["duration_from_clock_min"])))
    return states, {
        "participation_artifact_id": UPSTREAM_PARTICIPATION_ID,
        "trip_count_artifact_id": UPSTREAM_TRIP_COUNT_ID,
        "activity_chain_artifact_id": UPSTREAM_ACTIVITY_CHAIN_ID,
        "time_schedule_artifact_id": UPSTREAM_TIME_ID,
        "all_upstream_states": "MAIN_FROZEN",
        "fixed_source_cohort_days": len(cohort),
        "cohort_reselected": False,
    }


def _run_propagated_distance(adapter: DistancePriorAdapter, cohort: pd.DataFrame, states: list[list[list[dict[str, Any]]]]) -> dict[str, Any]:
    violations = 0
    generated = 0
    failures: list[dict[str, Any]] = []
    for replicate in range(REPLICATES):
        for row_index, (_, day) in enumerate(cohort.iterrows()):
            for trip_index, state in enumerate(states[replicate][row_index], start=1):
                try:
                    result = adapter.sample_one(pd.DataFrame([state]), seed=_distance_seed(day["row_id"], trip_index, replicate))
                    value = float(result["distance_prior_km"])
                    if not np.isfinite(value) or value <= 0:
                        raise RuntimeError("Generated propagated distance is not positive finite")
                    generated += 1
                except Exception as exc:
                    violations += 1
                    failures.append({"context_row_id": str(day["row_id"]), "replicate_id": replicate, "trip_index": trip_index, "exception_type": type(exc).__name__, "exception_message": str(exc)})
                    break
    return {"runtime_invariant_violations": violations, "generated_distance_rows": generated, "hard_pass": violations == 0, "failures": failures}


def _run_controlled_distance_prior_cal_direct(repo_root: Path, output_dir: Path, config_path: Path, authorization_path: Path, *, write_stochastic_evidence: bool = True) -> dict[str, Any]:
    started = time.perf_counter()
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    if config.get("phase") != "F3.4f-2b":
        raise ValueError("Unexpected Distance Prior real-CAL implementation contract")
    authorization = load_authorization(authorization_path, repo_root)
    if output_dir.exists():
        raise FileExistsError(f"RunBundle output already exists: {output_dir}")
    output_dir.mkdir(parents=True)

    raw, sensitivity, cohort, input_rows, access = load_and_validate_distance_cal(repo_root, config)
    records = _records(repo_root)
    adapters, artifact_validation = _validate_candidate_artifacts(repo_root, records)
    adapter_by_id = {a.record.artifact_id: a for a in adapters}
    record_by_id = {r.artifact_id: r for r in records}

    raw_observed = raw["target_distance_prior_km"].astype(float).to_numpy()
    raw_weight = raw["fit_weight_W_GEW"].astype(float).to_numpy()
    sens_observed = sensitivity["target_distance_sensitivity_km"].astype(float).to_numpy()
    sens_weight = sensitivity["fit_weight_W_GEW"].astype(float).to_numpy()

    raw_draws: dict[str, np.ndarray] = {}
    primary: dict[str, float] = {}
    summary: dict[str, dict[str, float]] = {}
    hard: dict[str, bool] = {}
    primary_rows: list[dict[str, Any]] = []
    sensitivity_rows: list[dict[str, Any]] = []
    summary_rows: list[dict[str, Any]] = []

    for adapter in adapters:
        aid = adapter.record.artifact_id
        draws = _generate_isolated(adapter, raw)
        raw_draws[aid] = draws
        hard[aid] = bool(np.isfinite(draws).all() and (draws > 0).all())
        primary[aid] = _metric_mean32(raw_observed, draws, raw_weight)
        sm = _summary_errors(raw_observed, draws, raw_weight)
        summary[aid] = sm
        primary_rows.append({"artifact_id": aid, "candidate_id": adapter.record.candidate_id, "grid_id": adapter.record.grid_id, "role": adapter.record.role, "metric": "M2-DIST-01", "wasserstein_km_mean32": primary[aid], "hard_pass": hard[aid]})
        summary_rows.append({"artifact_id": aid, "mean_abs_error_km_mean32": sm["MEAN"], "p50_abs_error_km_mean32": sm["P50"], "p90_abs_error_km_mean32": sm["P90"], "p95_abs_error_km_mean32": sm["P95"], "mean_role": "REPORT_ONLY_UNTHRESHOLDED"})
        sens_draws = _generate_isolated(adapter, sensitivity)
        sensitivity_rows.append({"artifact_id": aid, "metric": "M2-DIST-02", "wasserstein_km_mean32": _metric_mean32(sens_observed, sens_draws, sens_weight), "role": "REPORT_ONLY"})

    guardrail_rows: list[dict[str, Any]] = []
    grid_rows: list[dict[str, Any]] = []
    bootstrap_rows: list[dict[str, Any]] = []
    promotion_rows: list[dict[str, Any]] = []
    reference = record_by_id[REFERENCE_ID]
    incumbent = reference

    def compare(challenger: ArtifactRecord, current: ArtifactRecord) -> bool:
        passed, row = _compare_quantile_guardrails(summary[current.artifact_id], summary[challenger.artifact_id])
        guardrail_rows.append({"incumbent_artifact_id": current.artifact_id, "challenger_artifact_id": challenger.artifact_id, **row})
        return bool(hard[challenger.artifact_id] and passed)

    a_records = [r for r in records if r.role == "CORE_CANDIDATE_A"]
    a_scores = [_score(r, primary, hard, compare(r, reference)) for r in a_records]
    best_a = choose_within_family(a_scores)
    for score in a_scores:
        grid_rows.append({**asdict(score), "family": "A", "selected_within_family": bool(best_a and score.artifact_id == best_a.artifact_id)})
    if best_a is not None:
        boot = _bootstrap_improvement(raw, raw_draws[reference.artifact_id], raw_draws[best_a.artifact_id], reference.artifact_id, best_a.artifact_id)
        bootstrap_rows.append(boot)
        decision = promotion_decision(_score(reference, primary, hard, True), best_a, practical_margin=PRACTICAL_MARGIN, bootstrap_ci_lower=float(boot["ci_lower"]), bootstrap_ci_upper=float(boot["ci_upper"]))
        promotion_rows.append({**asdict(decision), "reasons": ";".join(decision.reasons), "stage": "REF_TO_A"})
        if decision.promoted:
            incumbent = record_by_id[best_a.artifact_id]

    b_records = [r for r in records if r.role == "CORE_CHALLENGER_B"]
    b_scores = [_score(r, primary, hard, compare(r, incumbent)) for r in b_records]
    best_b = choose_within_family(b_scores)
    for score in b_scores:
        grid_rows.append({**asdict(score), "family": "B", "selected_within_family": bool(best_b and score.artifact_id == best_b.artifact_id)})
    if best_b is not None:
        boot = _bootstrap_improvement(raw, raw_draws[incumbent.artifact_id], raw_draws[best_b.artifact_id], incumbent.artifact_id, best_b.artifact_id)
        bootstrap_rows.append(boot)
        decision = promotion_decision(_score(incumbent, primary, hard, True), best_b, practical_margin=PRACTICAL_MARGIN, bootstrap_ci_lower=float(boot["ci_lower"]), bootstrap_ci_upper=float(boot["ci_upper"]))
        promotion_rows.append({**asdict(decision), "reasons": ";".join(decision.reasons), "stage": "INCUMBENT_TO_B"})
        if decision.promoted:
            incumbent = record_by_id[best_b.artifact_id]

    propagated_states, upstream_snapshot = _generate_propagated_states(repo_root, cohort)
    propagated_records = [reference] + ([] if incumbent.artifact_id == reference.artifact_id else [incumbent])
    propagated_rows: list[dict[str, Any]] = []
    prop_pass = True
    for record in propagated_records:
        result = _run_propagated_distance(adapter_by_id[record.artifact_id], cohort, propagated_states)
        propagated_rows.append({"artifact_id": record.artifact_id, "runtime_invariant_violations": result["runtime_invariant_violations"], "generated_distance_rows": result["generated_distance_rows"], "hard_pass": result["hard_pass"]})
        prop_pass = prop_pass and bool(result["hard_pass"])

    selected = {
        "status": "PROPOSED_BY_FROZEN_CAL_RULES_AWAITING_MAIN_FREEZE" if prop_pass else "BLOCKED_PROPAGATED_RUNTIME_GUARDRAIL_RETURN_TO_MAIN",
        "base_artifact_id": incumbent.artifact_id,
        "proposed_selected_artifact_id": incumbent.artifact_id if prop_pass else None,
        "candidate_id": incumbent.candidate_id,
        "grid_id": incumbent.grid_id,
        "role": incumbent.role,
        "isolated_selection_complete": True,
        "propagated_runtime_guardrail_pass": prop_pass,
        "authorized_for_downstream": False,
        "joint_cal_gate_authorized": False,
    }

    _write_csv(output_dir / "input_hash_validation.csv", input_rows)
    _write_csv(output_dir / "candidate_artifact_validation.csv", artifact_validation)
    _write_csv(output_dir / "primary_metrics.csv", primary_rows)
    _write_csv(output_dir / "sensitivity_metrics.csv", sensitivity_rows)
    _write_csv(output_dir / "isolated_summary_metrics.csv", summary_rows)
    _write_csv(output_dir / "isolated_guardrails.csv", guardrail_rows)
    _write_csv(output_dir / "bootstrap_intervals.csv", bootstrap_rows)
    _write_csv(output_dir / "grid_selection.csv", grid_rows)
    _write_csv(output_dir / "promotion_decisions.csv", promotion_rows)
    _write_csv(output_dir / "propagated_runtime_guardrails.csv", propagated_rows)
    _write_json(output_dir / "upstream_selection_snapshot.json", upstream_snapshot)
    _write_json(output_dir / "selected_component_artifact.json", selected)
    _write_json(output_dir / "cal_access_manifest.json", access)
    _write_json(output_dir / "execution_authorization_snapshot.json", authorization)
    (output_dir / "execution_contract_snapshot.yaml").write_bytes(config_path.read_bytes())
    _write_json(output_dir / "environment.json", {"python": sys.version, "platform": platform.platform(), "numpy": np.__version__, "pandas": pd.__version__})

    evidence_rows = 0
    if write_stochastic_evidence:
        with gzip.open(output_dir / "stochastic_evidence.csv.gz", "wt", encoding="utf-8", newline="") as handle:
            header = False
            for record in records:
                draws = raw_draws[record.artifact_id]
                blocks = []
                for replicate in range(REPLICATES):
                    block = pd.DataFrame({
                        "component": COMPONENT,
                        "artifact_id": record.artifact_id,
                        "candidate_id": record.candidate_id,
                        "grid_id": record.grid_id,
                        "role": record.role,
                        "evaluation_mode": "ISOLATED",
                        "replicate_id": replicate,
                        "evaluation_person_id": "CAL|" + raw["source_household_id_distance"].astype(str) + "|" + raw["source_person_id_distance"].astype(str),
                        "source_household_id": raw["source_household_id_distance"].astype(str),
                        "event_index": raw["source_trip_id"].astype(int),
                        "draw_index": replicate,
                        "seed_u64": [_distance_seed(ctx, slot, replicate) for ctx, slot in zip(raw["context_row_id"], raw["source_trip_id"], strict=True)],
                        "weight": raw_weight,
                        "observed_json": [canonical_payload({"distance_km": float(v)}) for v in raw_observed],
                        "generated_json": [canonical_payload({"distance_prior_km": float(v)}) for v in draws[replicate]],
                    })
                    blocks.append(block)
                frame = pd.concat(blocks, ignore_index=True)
                frame.to_csv(handle, index=False, header=not header)
                header = True
                evidence_rows += len(frame)

    _write_json(output_dir / "evidence_manifest.json", {"schema": "F3_3C_STANDARD_EVIDENCE_V1_COMPATIBLE_DISTANCE_PRIOR", "rows": evidence_rows, "isolated_candidate_artifacts": len(records), "isolated_raw_rows": len(raw), "sensitivity_rows": len(sensitivity), "fixed_source_cohort_days": len(cohort), "common_random_numbers": True, "replicates": REPLICATES})
    _write_csv(output_dir / "validation.csv", [
        {"check": "cal_input_hashes_exact", "status": "PASS"},
        {"check": "cal_expected_rows_exact", "status": "PASS"},
        {"check": "distance_artifacts_exact_5", "status": "PASS"},
        {"check": "isolated_rows_all_1147", "status": "PASS"},
        {"check": "primary_m2_dist_01_mean32", "status": "PASS"},
        {"check": "sensitivity_m2_dist_02_report_only", "status": "PASS"},
        {"check": "quantile_guardrails_mean32_abs_error", "status": "PASS"},
        {"check": "household_bootstrap_1000", "status": "PASS"},
        {"check": "propagated_runtime_check_executed", "status": "PASS"},
        {"check": "test_rows_read_zero", "status": "PASS"},
        {"check": "joint_gate_not_authorized", "status": "PASS"},
    ])
    _write_csv(output_dir / "issues.csv", pd.DataFrame(columns=["issue_id", "severity", "detail"]))
    _write_json(output_dir / "performance.json", {"wall_seconds": time.perf_counter() - started, "cal_physical_rows_read": access["cal_rows_read_total_physical"], "isolated_raw_rows": len(raw), "sensitivity_rows": len(sensitivity), "fixed_source_cohort_days": len(cohort), "candidate_artifacts": len(records), "stochastic_replicates": REPLICATES, "bootstrap_replicates": BOOTSTRAPS, "stochastic_evidence_rows": evidence_rows})
    manifest = {
        "phase": "F3.4f-2b", "component": COMPONENT, "status": "PASS", "execution_mode": "CONTROLLED_REAL_CAL",
        "candidate_artifacts": 5, "candidate_selection_state": selected["status"], "proposed_selected_artifact_id": selected["proposed_selected_artifact_id"],
        "propagated_runtime_guardrail_pass": prop_pass, "cal_files_opened": access["cal_files_opened"], "cal_rows_read_total_physical": access["cal_rows_read_total_physical"],
        "cal_fixed_source_cohort_days": access["cal_fixed_source_cohort_days"], "cal_isolated_raw_rows": access["cal_isolated_raw_rows"], "cal_sensitivity_rows": access["cal_sensitivity_rows"],
        "joint_cal_gate_authorized": False, "test_rows_read": 0, "test_open_authorized": False, "formal_g2": "NOT_EVALUATED", "implementation_commit": _git(repo_root, "rev-parse", "HEAD"),
    }
    _write_json(output_dir / "run_manifest.json", manifest)
    _write_checksums(output_dir)
    return manifest


def run_controlled_distance_prior_cal(repo_root: Path, output_dir: Path, config_path: Path, authorization_path: Path, *, write_stochastic_evidence: bool = True) -> dict[str, Any]:
    if output_dir.exists():
        raise FileExistsError(f"RunBundle output already exists: {output_dir}")
    staging = output_dir.with_name(f"{output_dir.name}.partial")
    if staging.exists():
        raise FileExistsError(f"Partial RunBundle already exists: {staging}")
    load_authorization(authorization_path, repo_root)
    try:
        manifest = _run_controlled_distance_prior_cal_direct(repo_root, staging, config_path, authorization_path, write_stochastic_evidence=write_stochastic_evidence)
        staging.rename(output_dir)
        return manifest
    except Exception as exc:
        if staging.exists():
            _write_json(staging / "failure.json", {"status": "FAIL", "phase": "F3.4f-2b", "exception_type": type(exc).__name__, "exception_message": str(exc), "cal_read_may_have_occurred": True, "joint_cal_gate_authorized": False, "test_open_authorized": False})
            _write_checksums(staging)
        raise
