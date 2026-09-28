"""F3.4b-2 controlled real-CAL evaluation for DG_PARTICIPATION.

The module is inert with respect to CAL until the caller supplies an external
F3.4b-2b authorization bound to the exact committed implementation SHA.
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
from scipy.optimize import minimize
from scipy.special import expit, logit

from simfleet_edg.evaluation.cal_access_guard import PartitionAccess
from simfleet_edg.evaluation.cal_adapter_common import (
    ArtifactRecord,
    load_registry,
    sha256_file,
)
from simfleet_edg.evaluation.cal_bootstrap import (
    household_bootstrap_multipliers,
    percentile_interval,
)
from simfleet_edg.evaluation.cal_calibration import sigmoid_calibration_decision
from simfleet_edg.evaluation.cal_evidence import canonical_payload
from simfleet_edg.evaluation.cal_harness import evaluation_person_id, packed_draw_index
from simfleet_edg.evaluation.cal_metrics import weighted_bernoulli_logloss
from simfleet_edg.evaluation.cal_protocol import (
    CAL_SCENARIO_ID,
    MASTER_SEED,
    bootstrap_seed,
    part_b_household_fold,
    runtime_draw_seed,
)
from simfleet_edg.evaluation.cal_selection import (
    GridScore,
    choose_within_family,
    promotion_decision,
)
from simfleet_edg.evaluation.participation_adapter import ParticipationAdapter

COMPONENT = "DG_PARTICIPATION"
REPLICATES = 32
BOOTSTRAPS = 1000
COND_DIMS = (
    "age_infr_class",
    "sex",
    "primary_activity_status",
    "household_size_class",
)
ALLOWED_FEATURE_COLUMNS = {
    "age_infr_class",
    "sex",
    "primary_activity_status",
    "household_size_class",
    "source_weekday",
    "source_season",
    "hh_car_stock_class",
    "hh_motorcycle_moped_stock_class",
    "hh_ebike_stock_class",
    "hh_bike_stock_class",
    "hh_carsharing_membership",
    "person_car_access",
    "person_bike_access",
    "person_ebike_access",
    "person_carsharing_membership",
}
ROLE_RANK = {
    "REFERENCE_BASELINE": 0,
    "CORE_CANDIDATE_A": 1,
    "CORE_CHALLENGER_B": 2,
}


def _git(repo_root: Path, *args: str) -> str:
    return subprocess.check_output(
        ["git", "-C", str(repo_root), *args],
        text=True,
    ).strip()


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _write_csv(path: Path, data: pd.DataFrame | list[dict[str, Any]]) -> None:
    frame = data if isinstance(data, pd.DataFrame) else pd.DataFrame(data)
    frame.to_csv(path, index=False)


def _write_checksums(output_dir: Path) -> None:
    target = output_dir / "checksums.sha256"
    rows = []
    for path in sorted(output_dir.iterdir()):
        if path.is_file() and path.name != target.name:
            rows.append(f"{sha256_file(path)}  {path.name}")
    target.write_text("\n".join(rows) + "\n", encoding="utf-8")


def load_authorization(path: Path, repo_root: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    current = _git(repo_root, "rev-parse", "HEAD")
    required = {
        "phase": "F3.4b-2b",
        "component": COMPONENT,
        "real_cal_open_authorized": True,
        "candidate_artifacts": 8,
        "candidate_selection_at_entry": "NONE",
        "test_open_authorized": False,
        "formal_g2": "NOT_EVALUATED",
    }
    for key, value in required.items():
        if payload.get(key) != value:
            raise PermissionError(f"Invalid execution authorization field {key}")
    if payload.get("authorized_implementation_commit") != current:
        raise PermissionError(
            "Authorization is not bound to current implementation commit"
        )
    if set(payload.get("allowed_cal_files", [])) != {
        "person_day_context.csv",
        "participation.csv",
    }:
        raise PermissionError("Authorization CAL file scope mismatch")
    if _git(repo_root, "status", "--porcelain"):
        raise PermissionError("Real CAL execution requires a clean worktree")
    if _git(repo_root, "branch", "--show-current") != "main":
        raise PermissionError("Real CAL execution requires main branch")
    if _git(repo_root, "rev-list", "--count", "origin/main..HEAD") != "0":
        raise PermissionError("Real CAL execution requires ahead=0")
    if _git(repo_root, "rev-list", "--count", "HEAD..origin/main") != "0":
        raise PermissionError("Real CAL execution requires behind=0")
    return payload


def _validate_input_file(
    path: Path,
    expected_sha: str,
    expected_rows: int,
) -> pd.DataFrame:
    if not path.is_file():
        raise FileNotFoundError(path)
    digest = sha256_file(path)
    if digest != expected_sha:
        raise ValueError(f"CAL input SHA mismatch for {path.name}")
    frame = pd.read_csv(path)
    if len(frame) != expected_rows:
        raise ValueError(
            f"CAL input row mismatch for {path.name}: "
            f"{len(frame)} != {expected_rows}"
        )
    return frame


def load_and_validate_participation_cal(
    repo_root: Path,
    cfg: dict[str, Any],
) -> tuple[pd.DataFrame, list[dict[str, Any]], dict[str, Any]]:
    PartitionAccess(cal_authorized=True, test_authorized=False).require_cal()
    root = repo_root / cfg["cal_input"]["root"]
    context_spec = cfg["cal_input"]["person_day_context"]
    target_spec = cfg["cal_input"]["participation"]
    context_path = root / context_spec["filename"]
    target_path = root / target_spec["filename"]

    context = _validate_input_file(
        context_path,
        context_spec["sha256"],
        int(context_spec["expected_rows"]),
    )
    target = _validate_input_file(
        target_path,
        target_spec["sha256"],
        int(target_spec["expected_rows"]),
    )

    required_context = {
        "row_id",
        "source_household_id",
        "source_person_id",
        "fit_weight_P_GEW",
        *ALLOWED_FEATURE_COLUMNS,
    }
    required_target = {
        "context_row_id",
        "source_household_id",
        "source_person_id",
        "target_trip_day",
        "fit_weight_P_GEW",
    }
    missing_context = sorted(required_context - set(context.columns))
    missing_target = sorted(required_target - set(target.columns))
    if missing_context:
        raise ValueError(f"Missing context columns: {missing_context}")
    if missing_target:
        raise ValueError(f"Missing participation columns: {missing_target}")
    if context["row_id"].duplicated().any():
        raise ValueError("CAL context row_id must be unique")
    if target["context_row_id"].duplicated().any():
        raise ValueError("CAL participation context_row_id must be unique")

    merged = target.merge(
        context,
        left_on="context_row_id",
        right_on="row_id",
        how="left",
        validate="one_to_one",
        suffixes=("_target", "_context"),
    )
    expected_eval = int(cfg["cal_input"]["expected_evaluation_rows"])
    if len(merged) != expected_eval or merged["row_id"].isna().any():
        raise ValueError("Participation/context CAL join failed")
    for field in ("source_household_id", "source_person_id"):
        left = merged[f"{field}_target"].astype(str)
        right = merged[f"{field}_context"].astype(str)
        if not left.equals(right):
            raise ValueError(f"{field} mismatch across CAL tables")

    weight_target = merged["fit_weight_P_GEW_target"].astype(float).to_numpy()
    weight_context = merged["fit_weight_P_GEW_context"].astype(float).to_numpy()
    if not np.allclose(
        weight_target,
        weight_context,
        rtol=0.0,
        atol=1e-12,
    ):
        raise ValueError("P_GEW mismatch across CAL tables")
    if not np.isfinite(weight_target).all() or np.any(weight_target <= 0):
        raise ValueError("Invalid P_GEW in CAL")

    target_values = merged["target_trip_day"].astype(int).to_numpy()
    if set(np.unique(target_values)) != {0, 1}:
        raise ValueError("CAL participation target must contain both classes 0/1")

    input_rows = [
        {
            "filename": context_path.name,
            "sha256": sha256_file(context_path),
            "rows": len(context),
            "status": "PASS",
        },
        {
            "filename": target_path.name,
            "sha256": sha256_file(target_path),
            "rows": len(target),
            "status": "PASS",
        },
    ]
    access = {
        "cal_partition": "OPENED_AUTHORIZED_F3_4B2B",
        "cal_files_opened": [
            str(context_path.relative_to(repo_root)),
            str(target_path.relative_to(repo_root)),
        ],
        "cal_file_rows": {
            context_path.name: len(context),
            target_path.name: len(target),
        },
        "cal_rows_read_total_physical": len(context) + len(target),
        "cal_evaluation_rows": len(merged),
        "test_partition": "SEALED",
        "test_files_opened": [],
        "test_rows_read": 0,
    }
    return merged, input_rows, access


def _records(repo_root: Path) -> list[ArtifactRecord]:
    registry_path = repo_root / "docs/F3_3_CANDIDATE_ARTIFACT_REGISTRY_v1.csv"
    records = [
        record
        for record in load_registry(registry_path)
        if record.component == COMPONENT
    ]
    if len(records) != 8:
        raise ValueError("Participation candidate universe must contain 8 artifacts")
    if {record.train_state for record in records} != {
        "FITTED_TRAIN_ONLY_NOT_SELECTED"
    }:
        raise ValueError("Unexpected Participation train_state")
    return sorted(
        records,
        key=lambda record: (ROLE_RANK[record.role], record.grid_id),
    )


def _adapter_probabilities(
    repo_root: Path,
    records: list[ArtifactRecord],
    merged: pd.DataFrame,
) -> tuple[dict[str, np.ndarray], pd.DataFrame, list[dict[str, Any]]]:
    probabilities: dict[str, np.ndarray] = {}
    long_rows: list[pd.DataFrame] = []
    validation: list[dict[str, Any]] = []
    person_ids = [
        evaluation_person_id(household, person)
        for household, person in zip(
            merged["source_household_id_target"],
            merged["source_person_id_target"],
        )
    ]
    for record in records:
        adapter = ParticipationAdapter(repo_root, record)
        required = set(adapter.required_columns)
        future = sorted(required - ALLOWED_FEATURE_COLUMNS)
        if future:
            raise ValueError(
                f"NFI/feature violation for {record.artifact_id}: {future}"
            )
        probability = adapter.probabilities(merged)
        invalid = (
            len(probability) != len(merged)
            or not np.isfinite(probability).all()
            or ((probability < 0) | (probability > 1)).any()
        )
        if invalid:
            raise ValueError(f"Invalid probabilities for {record.artifact_id}")
        probabilities[record.artifact_id] = probability
        long_rows.append(
            pd.DataFrame(
                {
                    "evaluation_person_id": person_ids,
                    "source_household_id": (
                        merged["source_household_id_target"].astype(str)
                    ),
                    "source_person_id": merged["source_person_id_target"].astype(str),
                    "artifact_id": record.artifact_id,
                    "candidate_id": record.candidate_id,
                    "grid_id": record.grid_id,
                    "role": record.role,
                    "target_trip_day": merged["target_trip_day"].astype(int),
                    "weight": merged["fit_weight_P_GEW_target"].astype(float),
                    "probability_trip_day": probability,
                }
            )
        )
        validation.append(
            {
                "artifact_id": record.artifact_id,
                "candidate_id": record.candidate_id,
                "grid_id": record.grid_id,
                "role": record.role,
                "train_state": record.train_state,
                "model_sha256": record.model_sha256,
                "manifest_sha256": record.manifest_sha256,
                "required_feature_count": len(required),
                "nofuture_violations": len(future),
                "status": "PASS",
            }
        )
    return probabilities, pd.concat(long_rows, ignore_index=True), validation


def _uniforms(
    merged: pd.DataFrame,
) -> tuple[np.ndarray, np.ndarray, list[str]]:
    person_ids = [
        evaluation_person_id(household, person)
        for household, person in zip(
            merged["source_household_id_target"],
            merged["source_person_id_target"],
        )
    ]
    uniforms = np.empty((REPLICATES, len(merged)), dtype=float)
    seeds = np.empty((REPLICATES, len(merged)), dtype=np.uint64)
    for replicate in range(REPLICATES):
        draw_index = packed_draw_index(replicate, 0)
        for index, person_id in enumerate(person_ids):
            seed = runtime_draw_seed(
                MASTER_SEED,
                CAL_SCENARIO_ID,
                person_id,
                COMPONENT,
                draw_index,
            )
            seeds[replicate, index] = seed
            uniforms[replicate, index] = np.random.default_rng(seed).random()
    return uniforms, seeds, person_ids


def _weighted_share(values: np.ndarray, weights: np.ndarray) -> float:
    return float(np.average(values.astype(float), weights=weights))


def _guardrail_metrics(
    merged: pd.DataFrame,
    probability: np.ndarray,
    uniforms: np.ndarray,
) -> tuple[dict[str, Any], pd.DataFrame, np.ndarray]:
    observed = merged["target_trip_day"].astype(int).to_numpy()
    weights = merged["fit_weight_P_GEW_target"].astype(float).to_numpy()
    observed_global = _weighted_share(observed, weights)
    draws = (uniforms < probability[np.newaxis, :]).astype(np.int8)
    generated_global = np.array(
        [_weighted_share(row, weights) for row in draws],
        dtype=float,
    )
    global_errors = np.abs(generated_global - observed_global)

    conditional_rows: list[dict[str, Any]] = []
    supported_rep_max = np.zeros(REPLICATES, dtype=float)
    supported_count = 0
    for dimension in COND_DIMS:
        values = merged[dimension].astype(str).to_numpy()
        for group in sorted(set(values.tolist())):
            mask = values == group
            source_n = int(mask.sum())
            observed_share = _weighted_share(observed[mask], weights[mask])
            generated_shares = np.array(
                [_weighted_share(row[mask], weights[mask]) for row in draws],
                dtype=float,
            )
            errors = np.abs(generated_shares - observed_share)
            support = "OK" if source_n >= 30 else "LOW_N"
            if support == "OK":
                supported_count += 1
                supported_rep_max = np.maximum(supported_rep_max, errors)
            conditional_rows.append(
                {
                    "group_dimension": dimension,
                    "group_value": group,
                    "source_n": source_n,
                    "support_status": support,
                    "observed_weighted_trip_day_share": observed_share,
                    "generated_weighted_trip_day_share_mean32": float(
                        generated_shares.mean()
                    ),
                    "absolute_error_mean32": float(errors.mean()),
                    "absolute_error_max32": float(errors.max()),
                }
            )
    if supported_count == 0:
        raise ValueError("No supported conditional CAL cells")
    summary = {
        "m2_part_01_observed_share": observed_global,
        "m2_part_01_generated_share_mean32": float(generated_global.mean()),
        "m2_part_01_abs_error_mean32": float(global_errors.mean()),
        "m2_cond_01_supported_cells": supported_count,
        "m2_cond_01_max_supported_abs_error_mean32": float(
            supported_rep_max.mean()
        ),
    }
    return summary, pd.DataFrame(conditional_rows), draws


def _bootstrap_improvement(
    merged: pd.DataFrame,
    incumbent_probability: np.ndarray,
    challenger_probability: np.ndarray,
    incumbent_id: str,
    challenger_id: str,
) -> dict[str, Any]:
    households = merged["source_household_id_target"].astype(str)
    multipliers = household_bootstrap_multipliers(
        households,
        replicates=BOOTSTRAPS,
        seed=bootstrap_seed(
            MASTER_SEED,
            COMPONENT,
            incumbent_id,
            challenger_id,
        ),
    )
    observed = merged["target_trip_day"].astype(int).to_numpy()
    base_weight = merged["fit_weight_P_GEW_target"].astype(float).to_numpy()
    improvements = np.empty(BOOTSTRAPS, dtype=float)
    for index, multiplier in enumerate(multipliers):
        weight = base_weight * multiplier
        incumbent_loss = weighted_bernoulli_logloss(
            observed,
            incumbent_probability,
            weight,
        )
        challenger_loss = weighted_bernoulli_logloss(
            observed,
            challenger_probability,
            weight,
        )
        improvements[index] = incumbent_loss - challenger_loss
    interval = percentile_interval(improvements, confidence_level=0.95)
    return {
        "incumbent_artifact_id": incumbent_id,
        "challenger_artifact_id": challenger_id,
        "bootstrap_replicates": BOOTSTRAPS,
        "ci_lower": interval.lower,
        "ci_median": interval.median,
        "ci_upper": interval.upper,
    }


def _fit_sigmoid(
    raw_probability: np.ndarray,
    observed: np.ndarray,
    weights: np.ndarray,
) -> tuple[float, float]:
    x = logit(np.clip(np.asarray(raw_probability, dtype=float), 1e-12, 1 - 1e-12))
    y = np.asarray(observed, dtype=float)
    w = np.asarray(weights, dtype=float)
    weight_sum = float(w.sum())

    def objective(theta: np.ndarray) -> tuple[float, np.ndarray]:
        z = theta[0] + theta[1] * x
        probability = expit(z)
        value = float(
            np.sum(w * (np.logaddexp(0.0, z) - y * z)) / weight_sum
        )
        residual = w * (probability - y) / weight_sum
        gradient = np.array(
            [residual.sum(), np.sum(residual * x)],
            dtype=float,
        )
        return value, gradient

    result = minimize(
        fun=lambda theta: objective(theta)[0],
        x0=np.array([0.0, 1.0]),
        jac=lambda theta: objective(theta)[1],
        method="L-BFGS-B",
        options={"maxiter": 500, "ftol": 1e-12, "gtol": 1e-8, "maxls": 50},
    )
    if not result.success or not np.isfinite(result.x).all():
        raise RuntimeError(
            f"Weighted sigmoid calibration failed: {result.message}"
        )
    return float(result.x[0]), float(result.x[1])


def _apply_sigmoid(
    raw_probability: np.ndarray,
    intercept: float,
    slope: float,
) -> np.ndarray:
    x = logit(np.clip(np.asarray(raw_probability, dtype=float), 1e-12, 1 - 1e-12))
    probability = expit(intercept + slope * x)
    return np.clip(probability, 1e-15, 1 - 1e-15)


def _part_b_calibration(
    merged: pd.DataFrame,
    record: ArtifactRecord,
    raw_probability: np.ndarray,
    uniforms: np.ndarray,
) -> dict[str, Any]:
    observed = merged["target_trip_day"].astype(int).to_numpy()
    weights = merged["fit_weight_P_GEW_target"].astype(float).to_numpy()
    households = merged["source_household_id_target"].astype(str).to_numpy()
    folds = np.array(
        [part_b_household_fold(household) for household in households],
        dtype=int,
    )
    crossfit = np.empty(len(merged), dtype=float)
    for fold in range(5):
        train_mask = folds != fold
        valid_mask = folds == fold
        if not train_mask.any() or not valid_mask.any():
            raise ValueError("PART_B CAL fold is empty")
        intercept, slope = _fit_sigmoid(
            raw_probability[train_mask],
            observed[train_mask],
            weights[train_mask],
        )
        crossfit[valid_mask] = _apply_sigmoid(
            raw_probability[valid_mask],
            intercept,
            slope,
        )

    raw_loss = weighted_bernoulli_logloss(
        observed,
        raw_probability,
        weights,
    )
    calibrated_loss = weighted_bernoulli_logloss(
        observed,
        crossfit,
        weights,
    )
    observed_share = _weighted_share(observed, weights)
    raw_probability_share_error = abs(
        _weighted_share(raw_probability, weights) - observed_share
    )
    calibrated_probability_share_error = abs(
        _weighted_share(crossfit, weights) - observed_share
    )
    raw_draws = (uniforms < raw_probability[np.newaxis, :]).astype(np.int8)
    calibrated_draws = (uniforms < crossfit[np.newaxis, :]).astype(np.int8)
    raw_share_error = float(
        np.mean(
            [
                abs(_weighted_share(row, weights) - observed_share)
                for row in raw_draws
            ]
        )
    )
    calibrated_share_error = float(
        np.mean(
            [
                abs(_weighted_share(row, weights) - observed_share)
                for row in calibrated_draws
            ]
        )
    )
    decision = sigmoid_calibration_decision(
        uncalibrated_logloss=raw_loss,
        calibrated_logloss=calibrated_loss,
        uncalibrated_share_error=raw_share_error,
        calibrated_share_error=calibrated_share_error,
        min_logloss_gain=0.002,
        max_share_error_worsening=0.005,
    )
    result: dict[str, Any] = {
        "status": "EVALUATED_POST_BASE_SELECTION",
        "base_artifact_id": record.artifact_id,
        "folds": 5,
        "fold_unit": "HOUSEHOLD",
        "uncalibrated_logloss": raw_loss,
        "crossfit_calibrated_logloss": calibrated_loss,
        "logloss_gain": decision.logloss_gain,
        "uncalibrated_probability_share_error_report_only": (
            raw_probability_share_error
        ),
        "crossfit_calibrated_probability_share_error_report_only": (
            calibrated_probability_share_error
        ),
        "uncalibrated_m2_part_01_abs_error_mean32": raw_share_error,
        "crossfit_calibrated_m2_part_01_abs_error_mean32": (
            calibrated_share_error
        ),
        "share_error_worsening": decision.trip_day_share_error_worsening,
        "retained": decision.retained,
    }
    if decision.retained:
        intercept, slope = _fit_sigmoid(
            raw_probability,
            observed,
            weights,
        )
        result["final_fit_on_all_cal"] = {
            "calibrator_type": "WEIGHTED_SIGMOID_V1",
            "intercept": intercept,
            "slope": slope,
            "derived_artifact_id": (
                f"{record.artifact_id}::CAL_SIGMOID_V1"
            ),
        }
    return result


def _candidate_score(
    record: ArtifactRecord,
    primary_by_id: dict[str, float],
    guardrails_pass: bool,
) -> GridScore:
    return GridScore(
        artifact_id=record.artifact_id,
        candidate_id=record.candidate_id,
        grid_id=record.grid_id,
        role=record.role,
        primary_metric=float(primary_by_id[record.artifact_id]),
        hard_pass=True,
        guardrails_pass=guardrails_pass,
    )


def _run_controlled_participation_cal_direct(
    repo_root: Path,
    output_dir: Path,
    config_path: Path,
    authorization_path: Path,
    *,
    write_stochastic_evidence: bool = True,
) -> dict[str, Any]:
    started = time.perf_counter()
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    if config.get("phase") != "F3.4b-2a":
        raise ValueError("Unexpected real-CAL implementation contract")
    authorization = load_authorization(authorization_path, repo_root)
    if output_dir.exists():
        raise FileExistsError(f"RunBundle output already exists: {output_dir}")
    output_dir.mkdir(parents=True)

    merged, input_rows, access = load_and_validate_participation_cal(
        repo_root,
        config,
    )
    records = _records(repo_root)
    probabilities, probability_frame, artifact_validation = _adapter_probabilities(
        repo_root,
        records,
        merged,
    )
    uniforms, seeds, person_ids = _uniforms(merged)
    observed = merged["target_trip_day"].astype(int).to_numpy()
    weights = merged["fit_weight_P_GEW_target"].astype(float).to_numpy()

    primary_rows: list[dict[str, Any]] = []
    candidate_guardrails: list[dict[str, Any]] = []
    conditional_all: list[pd.DataFrame] = []
    draw_map: dict[str, np.ndarray] = {}
    record_map = {record.artifact_id: record for record in records}

    for record in records:
        probability = probabilities[record.artifact_id]
        primary = weighted_bernoulli_logloss(
            observed,
            probability,
            weights,
        )
        summary, conditional, draws = _guardrail_metrics(
            merged,
            probability,
            uniforms,
        )
        draw_map[record.artifact_id] = draws
        primary_rows.append(
            {
                "artifact_id": record.artifact_id,
                "candidate_id": record.candidate_id,
                "grid_id": record.grid_id,
                "role": record.role,
                "primary_metric": "WEIGHTED_BERNOULLI_LOG_LOSS",
                "value": primary,
                "hard_pass": True,
            }
        )
        candidate_guardrails.append(
            {"artifact_id": record.artifact_id, **summary}
        )
        conditional.insert(0, "artifact_id", record.artifact_id)
        conditional_all.append(conditional)

    primary_frame = pd.DataFrame(primary_rows)
    guardrail_frame = pd.DataFrame(candidate_guardrails)
    guard_by_id = guardrail_frame.set_index("artifact_id").to_dict(
        orient="index"
    )
    primary_by_id = primary_frame.set_index("artifact_id")["value"].to_dict()
    reference = next(
        record for record in records if record.role == "REFERENCE_BASELINE"
    )
    guardrail_rows: list[dict[str, Any]] = []

    def compare_guardrails(
        candidate: ArtifactRecord,
        incumbent: ArtifactRecord,
    ) -> bool:
        candidate_metrics = guard_by_id[candidate.artifact_id]
        incumbent_metrics = guard_by_id[incumbent.artifact_id]
        global_worsening = (
            candidate_metrics["m2_part_01_abs_error_mean32"]
            - incumbent_metrics["m2_part_01_abs_error_mean32"]
        )
        conditional_worsening = (
            candidate_metrics["m2_cond_01_max_supported_abs_error_mean32"]
            - incumbent_metrics["m2_cond_01_max_supported_abs_error_mean32"]
        )
        passed = (
            global_worsening <= 0.01 + 1e-15
            and conditional_worsening <= 0.02 + 1e-15
        )
        guardrail_rows.append(
            {
                "incumbent_artifact_id": incumbent.artifact_id,
                "challenger_artifact_id": candidate.artifact_id,
                "m2_part_01_worsening": global_worsening,
                "m2_part_01_tolerance": 0.01,
                "m2_cond_01_worsening": conditional_worsening,
                "m2_cond_01_tolerance": 0.02,
                "guardrails_pass": passed,
            }
        )
        return passed

    grid_rows: list[dict[str, Any]] = []
    bootstrap_rows: list[dict[str, Any]] = []
    promotion_rows: list[dict[str, Any]] = []
    incumbent = reference

    a_records = [record for record in records if record.role == "CORE_CANDIDATE_A"]
    a_scores = [
        _candidate_score(
            record,
            primary_by_id,
            compare_guardrails(record, reference),
        )
        for record in a_records
    ]
    best_a = choose_within_family(a_scores)
    for score in a_scores:
        grid_rows.append(
            {
                **asdict(score),
                "family": "A",
                "selected_within_family": bool(
                    best_a and score.artifact_id == best_a.artifact_id
                ),
            }
        )
    if best_a is not None:
        bootstrap = _bootstrap_improvement(
            merged,
            probabilities[reference.artifact_id],
            probabilities[best_a.artifact_id],
            reference.artifact_id,
            best_a.artifact_id,
        )
        bootstrap_rows.append(bootstrap)
        reference_score = _candidate_score(
            reference,
            primary_by_id,
            True,
        )
        decision = promotion_decision(
            reference_score,
            best_a,
            practical_margin=0.005,
            bootstrap_ci_lower=float(bootstrap["ci_lower"]),
            bootstrap_ci_upper=float(bootstrap["ci_upper"]),
        )
        promotion_rows.append(
            {
                **asdict(decision),
                "reasons": ";".join(decision.reasons),
                "stage": "REF_TO_A",
            }
        )
        if decision.promoted:
            incumbent = record_map[best_a.artifact_id]

    b_records = [record for record in records if record.role == "CORE_CHALLENGER_B"]
    b_scores = [
        _candidate_score(
            record,
            primary_by_id,
            compare_guardrails(record, incumbent),
        )
        for record in b_records
    ]
    best_b = choose_within_family(b_scores)
    for score in b_scores:
        grid_rows.append(
            {
                **asdict(score),
                "family": "B",
                "selected_within_family": bool(
                    best_b and score.artifact_id == best_b.artifact_id
                ),
            }
        )
    if best_b is not None:
        incumbent_score = _candidate_score(
            incumbent,
            primary_by_id,
            True,
        )
        bootstrap = _bootstrap_improvement(
            merged,
            probabilities[incumbent.artifact_id],
            probabilities[best_b.artifact_id],
            incumbent.artifact_id,
            best_b.artifact_id,
        )
        bootstrap_rows.append(bootstrap)
        decision = promotion_decision(
            incumbent_score,
            best_b,
            practical_margin=0.005,
            bootstrap_ci_lower=float(bootstrap["ci_lower"]),
            bootstrap_ci_upper=float(bootstrap["ci_upper"]),
        )
        promotion_rows.append(
            {
                **asdict(decision),
                "reasons": ";".join(decision.reasons),
                "stage": "INCUMBENT_TO_B",
            }
        )
        if decision.promoted:
            incumbent = record_map[best_b.artifact_id]

    if incumbent.candidate_id == "PART_B":
        calibration = _part_b_calibration(
            merged,
            incumbent,
            probabilities[incumbent.artifact_id],
            uniforms,
        )
    else:
        calibration = {
            "status": "NOT_APPLICABLE_BASE_SELECTION_NOT_PART_B",
            "base_artifact_id": incumbent.artifact_id,
            "retained": False,
        }

    proposed_artifact_id = incumbent.artifact_id
    if calibration.get("retained"):
        proposed_artifact_id = calibration["final_fit_on_all_cal"][
            "derived_artifact_id"
        ]
    selected = {
        "status": "PROPOSED_BY_FROZEN_CAL_RULES_NOT_MAIN_FROZEN",
        "base_artifact_id": incumbent.artifact_id,
        "proposed_selected_artifact_id": proposed_artifact_id,
        "candidate_id": incumbent.candidate_id,
        "grid_id": incumbent.grid_id,
        "role": incumbent.role,
        "calibrator_retained": bool(calibration.get("retained", False)),
        "authorized_for_downstream": False,
        "next_component_authorized": False,
    }

    _write_csv(output_dir / "input_hash_validation.csv", input_rows)
    _write_csv(
        output_dir / "candidate_artifact_validation.csv",
        artifact_validation,
    )
    _write_csv(output_dir / "candidate_probabilities.csv", probability_frame)
    _write_csv(output_dir / "primary_metrics.csv", primary_frame)
    _write_csv(
        output_dir / "guardrail_candidate_metrics.csv",
        guardrail_frame,
    )
    _write_csv(
        output_dir / "conditional_guardrails.csv",
        pd.concat(conditional_all, ignore_index=True),
    )
    _write_csv(output_dir / "guardrails.csv", guardrail_rows)
    _write_csv(output_dir / "bootstrap_intervals.csv", bootstrap_rows)
    _write_csv(output_dir / "grid_selection.csv", grid_rows)
    _write_csv(output_dir / "promotion_decisions.csv", promotion_rows)

    evidence_rows = 0
    if write_stochastic_evidence:
        evidence_path = output_dir / "stochastic_evidence.csv.gz"
        with gzip.open(
            evidence_path,
            "wt",
            encoding="utf-8",
            newline="",
        ) as handle:
            header_written = False
            observed_json = [
                canonical_payload({"trip_day": int(value)})
                for value in observed
            ]
            household_ids = merged["source_household_id_target"].astype(str)
            for record in records:
                probability = probabilities[record.artifact_id]
                draws = draw_map[record.artifact_id]
                for replicate in range(REPLICATES):
                    draw_index = packed_draw_index(replicate, 0)
                    generated_json = [
                        canonical_payload(
                            {
                                "probability_trip_day": float(prob),
                                "trip_day": bool(draw),
                            }
                        )
                        for prob, draw in zip(
                            probability,
                            draws[replicate],
                        )
                    ]
                    frame = pd.DataFrame(
                        {
                            "component": COMPONENT,
                            "artifact_id": record.artifact_id,
                            "candidate_id": record.candidate_id,
                            "grid_id": record.grid_id,
                            "role": record.role,
                            "evaluation_mode": "ISOLATED",
                            "replicate_id": replicate,
                            "evaluation_person_id": person_ids,
                            "source_household_id": household_ids,
                            "event_index": 0,
                            "draw_index": draw_index,
                            "seed_u64": seeds[replicate],
                            "weight": weights,
                            "observed_json": observed_json,
                            "generated_json": generated_json,
                        }
                    )
                    frame.to_csv(
                        handle,
                        index=False,
                        header=not header_written,
                    )
                    header_written = True
                    evidence_rows += len(frame)

    _write_json(
        output_dir / "evidence_manifest.json",
        {
            "schema": "F3_3C_STANDARD_EVIDENCE_V1_COMPATIBLE_PARTICIPATION",
            "rows": evidence_rows,
            "expected_rows_if_materialized": len(records)
            * REPLICATES
            * len(merged),
            "common_random_numbers": True,
            "replicates": REPLICATES,
        },
    )
    _write_json(
        output_dir / "part_b_calibration_decision.json",
        calibration,
    )
    _write_json(
        output_dir / "selected_component_artifact.json",
        selected,
    )
    _write_json(output_dir / "cal_access_manifest.json", access)
    _write_json(
        output_dir / "execution_authorization_snapshot.json",
        authorization,
    )
    (output_dir / "execution_contract_snapshot.yaml").write_bytes(
        config_path.read_bytes()
    )
    _write_json(
        output_dir / "environment.json",
        {
            "python": sys.version,
            "platform": platform.platform(),
            "numpy": np.__version__,
            "pandas": pd.__version__,
        },
    )

    validations = [
        {"check": "cal_input_hashes_exact", "status": "PASS"},
        {"check": "cal_expected_rows_exact", "status": "PASS"},
        {"check": "evaluation_rows_460", "status": "PASS"},
        {"check": "participation_artifacts_exact_8", "status": "PASS"},
        {"check": "candidate_train_state_fitted_only", "status": "PASS"},
        {"check": "nofuture_feature_violations_zero", "status": "PASS"},
        {"check": "common_random_numbers_32", "status": "PASS"},
        {"check": "household_bootstrap_1000", "status": "PASS"},
        {"check": "test_rows_read_zero", "status": "PASS"},
        {"check": "downstream_not_authorized", "status": "PASS"},
    ]
    _write_csv(output_dir / "validation.csv", validations)
    _write_csv(
        output_dir / "issues.csv",
        pd.DataFrame(columns=["issue_id", "severity", "detail"]),
    )
    _write_json(
        output_dir / "performance.json",
        {
            "wall_seconds": time.perf_counter() - started,
            "cal_physical_rows_read": access["cal_rows_read_total_physical"],
            "cal_evaluation_rows": len(merged),
            "candidate_artifacts": len(records),
            "stochastic_replicates": REPLICATES,
            "bootstrap_replicates": BOOTSTRAPS,
            "stochastic_evidence_rows": evidence_rows,
        },
    )
    manifest = {
        "phase": "F3.4b-2b",
        "component": COMPONENT,
        "status": "PASS",
        "execution_mode": "CONTROLLED_REAL_CAL",
        "candidate_artifacts": 8,
        "candidate_selection_state": (
            "PROPOSED_BY_FROZEN_RULES_AWAITING_MAIN_FREEZE"
        ),
        "proposed_selected_artifact_id": proposed_artifact_id,
        "cal_files_opened": access["cal_files_opened"],
        "cal_rows_read_total_physical": access[
            "cal_rows_read_total_physical"
        ],
        "cal_evaluation_rows": access["cal_evaluation_rows"],
        "test_rows_read": 0,
        "next_component_authorized": False,
        "test_open_authorized": False,
        "formal_g2": "NOT_EVALUATED",
        "implementation_commit": _git(repo_root, "rev-parse", "HEAD"),
    }
    _write_json(output_dir / "run_manifest.json", manifest)
    _write_checksums(output_dir)
    return manifest


def run_controlled_participation_cal(
    repo_root: Path,
    output_dir: Path,
    config_path: Path,
    authorization_path: Path,
    *,
    write_stochastic_evidence: bool = True,
) -> dict[str, Any]:
    """Run official CAL atomically; preserve a .partial bundle on failure."""
    if output_dir.exists():
        raise FileExistsError(f"RunBundle output already exists: {output_dir}")
    staging = output_dir.with_name(f"{output_dir.name}.partial")
    if staging.exists():
        raise FileExistsError(f"Partial RunBundle already exists: {staging}")
    try:
        manifest = _run_controlled_participation_cal_direct(
            repo_root,
            staging,
            config_path,
            authorization_path,
            write_stochastic_evidence=write_stochastic_evidence,
        )
        staging.rename(output_dir)
        return manifest
    except Exception as exc:
        if staging.exists():
            _write_json(
                staging / "failure.json",
                {
                    "status": "FAIL",
                    "phase": "F3.4b-2b",
                    "exception_type": type(exc).__name__,
                    "exception_message": str(exc),
                    "cal_read_may_have_occurred": True,
                    "test_open_authorized": False,
                },
            )
            _write_checksums(staging)
        raise
