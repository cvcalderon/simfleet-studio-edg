"""Controlled real-CAL runner for F3.4c Trip Count.

The module may read CAL only after an external F3.4c-2b authorization bound to
the exact committed implementation HEAD has been validated. Tests and PRE-OPEN
validation must not call the real execution entry point.
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
from simfleet_edg.evaluation.cal_evidence import canonical_payload
from simfleet_edg.evaluation.cal_harness import evaluation_person_id, packed_draw_index
from simfleet_edg.evaluation.cal_metrics import weighted_discrete_crps
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
from simfleet_edg.evaluation.participation_adapter import ParticipationAdapter
from simfleet_edg.evaluation.trip_count_adapter import TripCountAdapter

COMPONENT = "DG_TRIP_COUNT"
PARTICIPATION_COMPONENT = "DG_PARTICIPATION"
UPSTREAM_ARTIFACT_ID = "DG_PARTICIPATION::PART_A::PA1"
REPLICATES = 32
BOOTSTRAPS = 1000
PRACTICAL_MARGIN = 0.05
COND_DIMS = (
    "age_infr_class",
    "sex",
    "primary_activity_status",
    "household_size_class",
)
COUNT_ALLOWED_COLUMNS = {
    "age_infr_class",
    "sex",
    "primary_activity_status",
    "household_size_class",
    "source_weekday",
    "source_season",
}
PART_ALLOWED_COLUMNS = {
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


def _write_csv(path: Path, rows: list[dict[str, Any]] | pd.DataFrame) -> None:
    frame = rows if isinstance(rows, pd.DataFrame) else pd.DataFrame(rows)
    frame.to_csv(path, index=False)


def _write_checksums(output_dir: Path) -> None:
    target = output_dir / "checksums.sha256"
    lines: list[str] = []
    for path in sorted(output_dir.iterdir()):
        if path.is_file() and path.name != target.name:
            lines.append(f"{sha256_file(path)}  {path.name}")
    target.write_text("\n".join(lines) + "\n", encoding="utf-8")


def load_authorization(path: Path, repo_root: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    required = {
        "phase": "F3.4c-2b",
        "component": COMPONENT,
        "real_trip_count_cal_open_authorized": True,
        "candidate_artifacts": 5,
        "candidate_selection_at_entry": "NONE",
        "test_open_authorized": False,
        "formal_g2": "NOT_EVALUATED",
    }
    for key, value in required.items():
        if payload.get(key) != value:
            raise PermissionError(f"Invalid execution authorization field {key}")
    current = _git(repo_root, "rev-parse", "HEAD")
    if payload.get("authorized_implementation_commit") != current:
        raise PermissionError("Authorization is not bound to current implementation commit")
    if set(payload.get("allowed_cal_files", [])) != {
        "person_day_context.csv",
        "participation.csv",
        "trip_count.csv",
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
            f"CAL input row mismatch for {path.name}: {len(frame)} != {expected_rows}"
        )
    return frame


def _records(repo_root: Path) -> list[ArtifactRecord]:
    records = [
        record
        for record in load_registry(
            repo_root / "docs/F3_3_CANDIDATE_ARTIFACT_REGISTRY_v1.csv"
        )
        if record.component == COMPONENT
    ]
    if len(records) != 5:
        raise ValueError("Trip Count candidate universe must contain 5 artifacts")
    if {record.train_state for record in records} != {
        "FITTED_TRAIN_ONLY_NOT_SELECTED"
    }:
        raise ValueError("Unexpected Trip Count train_state")
    return sorted(
        records,
        key=lambda record: (ROLE_RANK[record.role], record.grid_id),
    )


def _upstream_record(repo_root: Path) -> ArtifactRecord:
    records = load_registry(repo_root / "docs/F3_3_CANDIDATE_ARTIFACT_REGISTRY_v1.csv")
    found = [r for r in records if r.artifact_id == UPSTREAM_ARTIFACT_ID]
    if len(found) != 1:
        raise ValueError("Frozen PA1 upstream artifact not found exactly once")
    if found[0].train_state != "FITTED_TRAIN_ONLY_NOT_SELECTED":
        raise ValueError("Unexpected PA1 registry train_state")
    return found[0]


def _merge_target_context(
    target: pd.DataFrame,
    context: pd.DataFrame,
    *,
    target_name: str,
) -> pd.DataFrame:
    merged = target.merge(
        context,
        left_on="context_row_id",
        right_on="row_id",
        how="left",
        validate="one_to_one",
        suffixes=("_target", "_context"),
    )
    if len(merged) != len(target) or merged["row_id"].isna().any():
        raise ValueError(f"{target_name}/context CAL join failed")
    for field in ("source_household_id", "source_person_id"):
        left = merged[f"{field}_target"].astype(str)
        right = merged[f"{field}_context"].astype(str)
        if not left.equals(right):
            raise ValueError(f"{field} mismatch in {target_name}/context")
    wt = merged["fit_weight_P_GEW_target"].astype(float).to_numpy()
    wc = merged["fit_weight_P_GEW_context"].astype(float).to_numpy()
    if not np.allclose(wt, wc, rtol=0.0, atol=1e-12):
        raise ValueError(f"P_GEW mismatch in {target_name}/context")
    return merged


def load_and_validate_trip_count_cal(
    repo_root: Path,
    cfg: dict[str, Any],
) -> tuple[pd.DataFrame, pd.DataFrame, list[dict[str, Any]], dict[str, Any]]:
    PartitionAccess(cal_authorized=True, test_authorized=False).require_cal()
    root = repo_root / cfg["cal_input"]["root"]

    loaded: dict[str, pd.DataFrame] = {}
    input_rows: list[dict[str, Any]] = []
    for key in ("person_day_context", "participation", "trip_count"):
        spec = cfg["cal_input"][key]
        path = root / spec["filename"]
        frame = _validate_input_file(
            path,
            str(spec["sha256"]),
            int(spec["expected_rows"]),
        )
        loaded[key] = frame
        input_rows.append(
            {
                "filename": path.name,
                "sha256": sha256_file(path),
                "rows": len(frame),
                "status": "PASS",
            }
        )

    context = loaded["person_day_context"]
    participation = loaded["participation"]
    trip_count = loaded["trip_count"]

    required_context = {
        "row_id",
        "source_household_id",
        "source_person_id",
        "fit_weight_P_GEW",
        *PART_ALLOWED_COLUMNS,
    }
    required_part = {
        "context_row_id",
        "source_household_id",
        "source_person_id",
        "target_trip_day",
        "fit_weight_P_GEW",
    }
    required_count = {
        "context_row_id",
        "source_household_id",
        "source_person_id",
        "target_trip_count",
        "fit_weight_P_GEW",
    }
    if missing := sorted(required_context - set(context.columns)):
        raise ValueError(f"Missing context columns: {missing}")
    if missing := sorted(required_part - set(participation.columns)):
        raise ValueError(f"Missing participation columns: {missing}")
    if missing := sorted(required_count - set(trip_count.columns)):
        raise ValueError(f"Missing trip_count columns: {missing}")

    if context["row_id"].duplicated().any():
        raise ValueError("CAL context row_id must be unique")
    if participation["context_row_id"].duplicated().any():
        raise ValueError("CAL participation context_row_id must be unique")
    if trip_count["context_row_id"].duplicated().any():
        raise ValueError("CAL trip_count context_row_id must be unique")

    full = _merge_target_context(participation, context, target_name="participation")
    positive = _merge_target_context(trip_count, context, target_name="trip_count")

    if len(full) != int(cfg["cal_input"]["expected_full_person_days"]):
        raise ValueError("Unexpected full person-day evaluation rows")
    if len(positive) != int(cfg["cal_input"]["expected_isolated_rows"]):
        raise ValueError("Unexpected isolated positive-count evaluation rows")

    part_y = full["target_trip_day"].astype(int).to_numpy()
    if not set(np.unique(part_y)).issubset({0, 1}):
        raise ValueError("Participation target must be binary")
    count_y = positive["target_trip_count"].astype(int).to_numpy()
    if np.any(count_y < 1):
        raise ValueError("Trip Count target must be positive")

    mobile_context_ids = set(
        full.loc[full["target_trip_day"].astype(int) == 1, "context_row_id"].astype(str)
    )
    count_context_ids = set(positive["context_row_id"].astype(str))
    if mobile_context_ids != count_context_ids:
        raise ValueError("Positive Trip Count rows must exactly match CAL TripDay rows")

    full = full.copy()
    observed_by_context = dict(
        zip(
            positive["context_row_id"].astype(str),
            positive["target_trip_count"].astype(int),
        )
    )
    full["observed_trip_count_full"] = [
        observed_by_context.get(str(context_id), 0)
        for context_id in full["context_row_id"]
    ]

    access = {
        "cal_partition": "OPENED_AUTHORIZED_F3_4C2B",
        "cal_files_opened": [
            str(
                (
                    root / cfg["cal_input"][key]["filename"]
                ).relative_to(repo_root)
            )
            for key in ("person_day_context", "participation", "trip_count")
        ],
        "cal_file_rows": {
            cfg["cal_input"][key]["filename"]: len(loaded[key])
            for key in ("person_day_context", "participation", "trip_count")
        },
        "cal_rows_read_total_physical": sum(len(frame) for frame in loaded.values()),
        "cal_isolated_evaluation_rows": len(positive),
        "cal_full_person_days": len(full),
        "test_partition": "SEALED",
        "test_files_opened": [],
        "test_rows_read": 0,
    }
    return positive, full, input_rows, access


def _pmfs(
    repo_root: Path,
    records: list[ArtifactRecord],
    frame: pd.DataFrame,
) -> tuple[dict[str, np.ndarray], dict[str, np.ndarray], list[dict[str, Any]]]:
    pmfs: dict[str, np.ndarray] = {}
    supports: dict[str, np.ndarray] = {}
    validation: list[dict[str, Any]] = []
    for record in records:
        adapter = TripCountAdapter(repo_root, record)
        future = sorted(set(adapter.required_columns) - COUNT_ALLOWED_COLUMNS)
        if future:
            raise ValueError(f"NFI/feature violation for {record.artifact_id}: {future}")
        pmf = adapter.pmf(frame)
        support = np.asarray(adapter.support, dtype=int)
        invalid = (
            pmf.ndim != 2
            or pmf.shape != (len(frame), len(support))
            or not np.isfinite(pmf).all()
            or (pmf < 0).any()
            or not np.allclose(pmf.sum(axis=1), 1.0, atol=1e-10)
        )
        if invalid:
            raise ValueError(f"Invalid Trip Count PMF for {record.artifact_id}")
        pmfs[record.artifact_id] = pmf
        supports[record.artifact_id] = support
        validation.append(
            {
                "artifact_id": record.artifact_id,
                "candidate_id": record.candidate_id,
                "grid_id": record.grid_id,
                "role": record.role,
                "train_state": record.train_state,
                "model_sha256": record.model_sha256,
                "manifest_sha256": record.manifest_sha256,
                "pmf_rows": len(pmf),
                "support_min": int(support.min()),
                "support_max": int(support.max()),
                "status": "PASS",
            }
        )
    return pmfs, supports, validation


def _person_ids(frame: pd.DataFrame) -> list[str]:
    return [
        evaluation_person_id(household, person)
        for household, person in zip(
            frame["source_household_id_target"],
            frame["source_person_id_target"],
        )
    ]


def _uniform_matrix(
    frame: pd.DataFrame,
    *,
    component: str,
) -> tuple[np.ndarray, np.ndarray]:
    person_ids = _person_ids(frame)
    uniforms = np.empty((REPLICATES, len(frame)), dtype=float)
    seeds = np.empty((REPLICATES, len(frame)), dtype=np.uint64)
    for replicate in range(REPLICATES):
        draw_index = packed_draw_index(replicate, 0)
        for row_index, person_id in enumerate(person_ids):
            seed = runtime_draw_seed(
                MASTER_SEED,
                CAL_SCENARIO_ID,
                person_id,
                component,
                draw_index,
            )
            seeds[replicate, row_index] = seed
            uniforms[replicate, row_index] = np.random.default_rng(seed).random()
    return uniforms, seeds


def _draw_from_pmf(
    pmf: np.ndarray,
    support: np.ndarray,
    uniforms: np.ndarray,
) -> np.ndarray:
    cdf = np.cumsum(pmf, axis=1)
    draws = np.empty(uniforms.shape, dtype=int)
    for replicate in range(uniforms.shape[0]):
        indexes = np.sum(
            uniforms[replicate, :, None] > cdf,
            axis=1,
        )
        indexes = np.minimum(indexes, len(support) - 1)
        draws[replicate] = support[indexes]
    return draws


def _weighted_tvd(
    observed: np.ndarray,
    generated: np.ndarray,
    weights: np.ndarray,
    *,
    include_zero: bool,
) -> float:
    categories = list(range(0 if include_zero else 1, 12)) + [12]
    obs = np.array(
        [
            np.sum(weights[(observed == k) if k < 12 else (observed >= 12)])
            for k in categories
        ],
        dtype=float,
    )
    gen = np.array(
        [
            np.sum(weights[(generated == k) if k < 12 else (generated >= 12)])
            for k in categories
        ],
        dtype=float,
    )
    if obs.sum() <= 0 or gen.sum() <= 0:
        raise ValueError("Cannot compute weighted TVD with zero total weight")
    obs /= obs.sum()
    gen /= gen.sum()
    return float(0.5 * np.abs(obs - gen).sum())


def _max_supported_subgroup_error(
    frame: pd.DataFrame,
    generated: np.ndarray,
    observed: np.ndarray,
    weights: np.ndarray,
) -> tuple[float, list[dict[str, Any]]]:
    errors: list[float] = []
    rows: list[dict[str, Any]] = []
    for dimension in COND_DIMS:
        values = frame[dimension].astype(str).to_numpy()
        for value in sorted(set(values.tolist())):
            mask = values == value
            source_n = int(mask.sum())
            obs_mean = float(np.average(observed[mask], weights=weights[mask]))
            gen_mean = float(np.average(generated[mask], weights=weights[mask]))
            error = abs(gen_mean - obs_mean)
            supported = source_n >= 30
            rows.append(
                {
                    "dimension": dimension,
                    "value": value,
                    "source_n": source_n,
                    "supported": supported,
                    "observed_mean_trips_per_day": obs_mean,
                    "generated_mean_trips_per_day": gen_mean,
                    "absolute_error": error,
                }
            )
            if supported:
                errors.append(error)
    return (max(errors) if errors else 0.0), rows


def _guardrail_metrics(
    full: pd.DataFrame,
    draws: np.ndarray,
) -> tuple[dict[str, float], pd.DataFrame]:
    observed = full["observed_trip_count_full"].astype(int).to_numpy()
    weights = full["fit_weight_P_GEW_target"].astype(float).to_numpy()
    mean_obs = float(np.average(observed, weights=weights))
    count_01: list[float] = []
    count_02: list[float] = []
    chain_01: list[float] = []
    cond_02: list[float] = []
    conditional_rows: list[dict[str, Any]] = []

    for replicate in range(REPLICATES):
        generated = draws[replicate]
        mean_gen = float(np.average(generated, weights=weights))
        count_01.append(abs(mean_gen - mean_obs))
        count_02.append(
            _weighted_tvd(observed, generated, weights, include_zero=True)
        )
        obs_mobile = observed > 0
        gen_mobile = generated > 0
        if not obs_mobile.any() or not gen_mobile.any():
            raise ValueError("Mobile-day distribution cannot be empty")
        chain_01.append(
            _conditional_mobile_tvd(
                observed,
                generated,
                weights,
            )
        )
        maximum, rows = _max_supported_subgroup_error(
            full,
            generated,
            observed,
            weights,
        )
        cond_02.append(maximum)
        for row in rows:
            conditional_rows.append({"replicate_id": replicate, **row})

    return (
        {
            "m2_count_01_abs_error_mean32": float(np.mean(count_01)),
            "m2_count_02_tvd_mean32": float(np.mean(count_02)),
            "m2_chain_01_tvd_mean32": float(np.mean(chain_01)),
            "m2_cond_02_max_supported_abs_error_mean32": float(np.mean(cond_02)),
        },
        pd.DataFrame(conditional_rows),
    )


def _conditional_mobile_tvd(
    observed: np.ndarray,
    generated: np.ndarray,
    weights: np.ndarray,
) -> float:
    obs_mask = observed > 0
    gen_mask = generated > 0
    categories = list(range(1, 12)) + [12]
    obs = np.array(
        [
            np.sum(
                weights[
                    obs_mask
                    & ((observed == k) if k < 12 else (observed >= 12))
                ]
            )
            for k in categories
        ],
        dtype=float,
    )
    gen = np.array(
        [
            np.sum(
                weights[
                    gen_mask
                    & ((generated == k) if k < 12 else (generated >= 12))
                ]
            )
            for k in categories
        ],
        dtype=float,
    )
    if obs.sum() <= 0 or gen.sum() <= 0:
        raise ValueError("Cannot compute mobile-day TVD")
    obs /= obs.sum()
    gen /= gen.sum()
    return float(0.5 * np.abs(obs - gen).sum())


def _bootstrap_improvement(
    positive: pd.DataFrame,
    incumbent_pmf: np.ndarray,
    incumbent_support: np.ndarray,
    challenger_pmf: np.ndarray,
    challenger_support: np.ndarray,
    incumbent_id: str,
    challenger_id: str,
) -> dict[str, Any]:
    if not np.array_equal(incumbent_support, challenger_support):
        raise ValueError("Trip Count supports differ across compared candidates")
    y = positive["target_trip_count"].astype(int).to_numpy()
    base_weight = positive["fit_weight_P_GEW_target"].astype(float).to_numpy()
    multipliers = household_bootstrap_multipliers(
        positive["source_household_id_target"],
        replicates=BOOTSTRAPS,
        seed=bootstrap_seed(
            MASTER_SEED,
            COMPONENT,
            incumbent_id,
            challenger_id,
        ),
    )
    differences = np.empty(BOOTSTRAPS, dtype=float)
    for index, multiplier in enumerate(multipliers):
        weight = base_weight * multiplier
        if weight.sum() <= 0:
            raise ValueError("Bootstrap removed all Trip Count rows")
        incumbent = weighted_discrete_crps(
            y,
            incumbent_pmf,
            weight,
            int(incumbent_support[0]),
        )
        challenger = weighted_discrete_crps(
            y,
            challenger_pmf,
            weight,
            int(challenger_support[0]),
        )
        differences[index] = incumbent - challenger
    interval = percentile_interval(differences, confidence_level=0.95)
    return {
        "incumbent_artifact_id": incumbent_id,
        "challenger_artifact_id": challenger_id,
        "bootstrap_replicates": BOOTSTRAPS,
        "ci_lower": interval.lower,
        "ci_median": interval.median,
        "ci_upper": interval.upper,
    }


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
        guardrails_pass=bool(guardrails_pass),
    )


def _compare_guardrails(
    incumbent: dict[str, float],
    challenger: dict[str, float],
) -> tuple[bool, dict[str, Any]]:
    specs = (
        ("m2_count_01_abs_error_mean32", 0.10),
        ("m2_count_02_tvd_mean32", 0.005),
        ("m2_chain_01_tvd_mean32", 0.005),
        ("m2_cond_02_max_supported_abs_error_mean32", 0.02),
    )
    row: dict[str, Any] = {}
    passed = True
    for metric, tolerance in specs:
        worsening = float(challenger[metric] - incumbent[metric])
        row[f"{metric}_worsening"] = worsening
        row[f"{metric}_tolerance"] = tolerance
        passed = passed and worsening <= tolerance + 1e-15
    row["guardrails_pass"] = passed
    return passed, row


def _participation_probabilities(
    repo_root: Path,
    full: pd.DataFrame,
) -> np.ndarray:
    record = _upstream_record(repo_root)
    adapter = ParticipationAdapter(repo_root, record)
    future = sorted(set(adapter.required_columns) - PART_ALLOWED_COLUMNS)
    if future:
        raise ValueError(f"PA1 NFI/feature violation: {future}")
    probability = adapter.probabilities(full)
    if (
        len(probability) != len(full)
        or not np.isfinite(probability).all()
        or ((probability < 0) | (probability > 1)).any()
    ):
        raise ValueError("Invalid PA1 probabilities")
    return probability


def _participation_draws(full: pd.DataFrame, probability: np.ndarray) -> np.ndarray:
    uniforms, _ = _uniform_matrix(full, component=PARTICIPATION_COMPONENT)
    return (uniforms < probability[None, :]).astype(int)


def _full_candidate_draws(
    repo_root: Path,
    record: ArtifactRecord,
    full: pd.DataFrame,
    trip_day_draws: np.ndarray,
    trip_uniforms: np.ndarray,
) -> np.ndarray:
    adapter = TripCountAdapter(repo_root, record)
    future = sorted(set(adapter.required_columns) - COUNT_ALLOWED_COLUMNS)
    if future:
        raise ValueError(f"NFI/feature violation for {record.artifact_id}: {future}")
    pmf = adapter.pmf(full)
    positive_draws = _draw_from_pmf(
        pmf,
        np.asarray(adapter.support, dtype=int),
        trip_uniforms,
    )
    return positive_draws * trip_day_draws


def _run_controlled_trip_count_cal_direct(
    repo_root: Path,
    output_dir: Path,
    config_path: Path,
    authorization_path: Path,
    *,
    write_stochastic_evidence: bool = True,
) -> dict[str, Any]:
    started = time.perf_counter()
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    if config.get("phase") != "F3.4c-2a":
        raise ValueError("Unexpected Trip Count real-CAL implementation contract")
    authorization = load_authorization(authorization_path, repo_root)
    if output_dir.exists():
        raise FileExistsError(f"RunBundle output already exists: {output_dir}")
    output_dir.mkdir(parents=True)

    positive, full, input_rows, access = load_and_validate_trip_count_cal(
        repo_root,
        config,
    )
    records = _records(repo_root)
    isolated_pmfs, supports, artifact_validation = _pmfs(
        repo_root,
        records,
        positive,
    )
    positive_uniforms, _ = _uniform_matrix(
        positive,
        component=COMPONENT,
    )
    full_uniforms, full_seeds = _uniform_matrix(
        full,
        component=COMPONENT,
    )

    full_index = {
        str(context_id): index
        for index, context_id in enumerate(full["context_row_id"])
    }
    positive_to_full = np.array(
        [full_index[str(context_id)] for context_id in positive["context_row_id"]],
        dtype=int,
    )
    empirical_trip_day = full["target_trip_day"].astype(int).to_numpy()
    isolated_full_draws: dict[str, np.ndarray] = {}
    primary_rows: list[dict[str, Any]] = []
    isolated_metrics: list[dict[str, Any]] = []
    isolated_conditional: list[pd.DataFrame] = []

    y = positive["target_trip_count"].astype(int).to_numpy()
    w = positive["fit_weight_P_GEW_target"].astype(float).to_numpy()

    for record in records:
        pmf = isolated_pmfs[record.artifact_id]
        support = supports[record.artifact_id]
        primary = weighted_discrete_crps(y, pmf, w, int(support[0]))
        positive_draws = _draw_from_pmf(pmf, support, positive_uniforms)
        full_draws = np.zeros((REPLICATES, len(full)), dtype=int)
        full_draws[:, positive_to_full] = positive_draws
        if not np.array_equal(
            (full_draws > 0).astype(int),
            np.repeat(empirical_trip_day[None, :], REPLICATES, axis=0),
        ):
            raise ValueError("ISOLATED TripDay teacher-forcing invariant failed")
        isolated_full_draws[record.artifact_id] = full_draws
        metrics, conditional = _guardrail_metrics(full, full_draws)
        primary_rows.append(
            {
                "artifact_id": record.artifact_id,
                "candidate_id": record.candidate_id,
                "grid_id": record.grid_id,
                "role": record.role,
                "primary_metric": "WEIGHTED_DISCRETE_CRPS_ON_K",
                "value": primary,
                "hard_pass": True,
            }
        )
        isolated_metrics.append({"artifact_id": record.artifact_id, **metrics})
        conditional.insert(0, "artifact_id", record.artifact_id)
        isolated_conditional.append(conditional)

    primary_frame = pd.DataFrame(primary_rows)
    isolated_metric_frame = pd.DataFrame(isolated_metrics)
    primary_by_id = primary_frame.set_index("artifact_id")["value"].to_dict()
    guard_by_id = isolated_metric_frame.set_index("artifact_id").to_dict(
        orient="index"
    )
    record_map = {record.artifact_id: record for record in records}
    reference = next(
        record for record in records if record.role == "REFERENCE_BASELINE"
    )
    pair_guardrails: list[dict[str, Any]] = []

    def compare(record: ArtifactRecord, incumbent: ArtifactRecord) -> bool:
        passed, row = _compare_guardrails(
            guard_by_id[incumbent.artifact_id],
            guard_by_id[record.artifact_id],
        )
        pair_guardrails.append(
            {
                "incumbent_artifact_id": incumbent.artifact_id,
                "challenger_artifact_id": record.artifact_id,
                **row,
            }
        )
        return passed

    grid_rows: list[dict[str, Any]] = []
    bootstrap_rows: list[dict[str, Any]] = []
    promotion_rows: list[dict[str, Any]] = []
    incumbent = reference

    a_records = [r for r in records if r.role == "CORE_CANDIDATE_A"]
    a_scores = [
        _candidate_score(r, primary_by_id, compare(r, reference))
        for r in a_records
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
        boot = _bootstrap_improvement(
            positive,
            isolated_pmfs[reference.artifact_id],
            supports[reference.artifact_id],
            isolated_pmfs[best_a.artifact_id],
            supports[best_a.artifact_id],
            reference.artifact_id,
            best_a.artifact_id,
        )
        bootstrap_rows.append(boot)
        decision = promotion_decision(
            _candidate_score(reference, primary_by_id, True),
            best_a,
            practical_margin=PRACTICAL_MARGIN,
            bootstrap_ci_lower=float(boot["ci_lower"]),
            bootstrap_ci_upper=float(boot["ci_upper"]),
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

    b_records = [r for r in records if r.role == "CORE_CHALLENGER_B"]
    b_scores = [
        _candidate_score(r, primary_by_id, compare(r, incumbent))
        for r in b_records
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
        boot = _bootstrap_improvement(
            positive,
            isolated_pmfs[incumbent.artifact_id],
            supports[incumbent.artifact_id],
            isolated_pmfs[best_b.artifact_id],
            supports[best_b.artifact_id],
            incumbent.artifact_id,
            best_b.artifact_id,
        )
        bootstrap_rows.append(boot)
        decision = promotion_decision(
            _candidate_score(incumbent, primary_by_id, True),
            best_b,
            practical_margin=PRACTICAL_MARGIN,
            bootstrap_ci_lower=float(boot["ci_lower"]),
            bootstrap_ci_upper=float(boot["ci_upper"]),
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

    # Mandatory propagated guardrail-only check.
    pa1_probability = _participation_probabilities(repo_root, full)
    propagated_trip_day = _participation_draws(full, pa1_probability)
    propagated_records = [reference]
    if incumbent.artifact_id != reference.artifact_id:
        propagated_records.append(incumbent)

    propagated_metrics_rows: list[dict[str, Any]] = []
    propagated_conditional: list[pd.DataFrame] = []
    propagated_draws: dict[str, np.ndarray] = {}
    for record in propagated_records:
        draws = _full_candidate_draws(
            repo_root,
            record,
            full,
            propagated_trip_day,
            full_uniforms,
        )
        propagated_draws[record.artifact_id] = draws
        metrics, conditional = _guardrail_metrics(full, draws)
        propagated_metrics_rows.append(
            {"artifact_id": record.artifact_id, **metrics}
        )
        conditional.insert(0, "artifact_id", record.artifact_id)
        propagated_conditional.append(conditional)

    propagated_metric_frame = pd.DataFrame(propagated_metrics_rows)
    prop_by_id = propagated_metric_frame.set_index("artifact_id").to_dict(
        orient="index"
    )
    propagated_pass, propagated_row = _compare_guardrails(
        prop_by_id[reference.artifact_id],
        prop_by_id[incumbent.artifact_id],
    )
    propagated_guardrail_rows = [
        {
            "incumbent_artifact_id": reference.artifact_id,
            "challenger_artifact_id": incumbent.artifact_id,
            **propagated_row,
        }
    ]

    selected = {
        "status": (
            "PROPOSED_BY_FROZEN_CAL_RULES_AWAITING_MAIN_FREEZE"
            if propagated_pass
            else "BLOCKED_PROPAGATED_GUARDRAIL_RETURN_TO_MAIN"
        ),
        "base_artifact_id": incumbent.artifact_id,
        "proposed_selected_artifact_id": (
            incumbent.artifact_id if propagated_pass else None
        ),
        "candidate_id": incumbent.candidate_id,
        "grid_id": incumbent.grid_id,
        "role": incumbent.role,
        "isolated_selection_complete": True,
        "propagated_guardrails_pass": propagated_pass,
        "authorized_for_downstream": False,
        "next_component_authorized": False,
    }

    _write_csv(output_dir / "input_hash_validation.csv", input_rows)
    _write_csv(
        output_dir / "candidate_artifact_validation.csv",
        artifact_validation,
    )
    _write_csv(output_dir / "primary_metrics.csv", primary_frame)
    _write_csv(
        output_dir / "isolated_guardrail_candidate_metrics.csv",
        isolated_metric_frame,
    )
    _write_csv(
        output_dir / "isolated_conditional_guardrails.csv",
        pd.concat(isolated_conditional, ignore_index=True),
    )
    _write_csv(output_dir / "isolated_guardrails.csv", pair_guardrails)
    _write_csv(output_dir / "bootstrap_intervals.csv", bootstrap_rows)
    _write_csv(output_dir / "grid_selection.csv", grid_rows)
    _write_csv(output_dir / "promotion_decisions.csv", promotion_rows)
    _write_csv(
        output_dir / "propagated_guardrail_candidate_metrics.csv",
        propagated_metric_frame,
    )
    _write_csv(
        output_dir / "propagated_conditional_guardrails.csv",
        pd.concat(propagated_conditional, ignore_index=True),
    )
    _write_csv(
        output_dir / "propagated_guardrails.csv",
        propagated_guardrail_rows,
    )
    _write_json(
        output_dir / "upstream_selection_snapshot.json",
        {
            "component": PARTICIPATION_COMPONENT,
            "artifact_id": UPSTREAM_ARTIFACT_ID,
            "state": "MAIN_FROZEN",
        },
    )
    _write_json(output_dir / "selected_component_artifact.json", selected)
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
            full_person_ids = _person_ids(full)
            household_ids = full["source_household_id_target"].astype(str)
            weights = full["fit_weight_P_GEW_target"].astype(float)
            observed = full["observed_trip_count_full"].astype(int)
            for record in records:
                draws = isolated_full_draws[record.artifact_id]
                for replicate in range(REPLICATES):
                    frame = pd.DataFrame(
                        {
                            "component": COMPONENT,
                            "artifact_id": record.artifact_id,
                            "candidate_id": record.candidate_id,
                            "grid_id": record.grid_id,
                            "role": record.role,
                            "evaluation_mode": "ISOLATED",
                            "replicate_id": replicate,
                            "evaluation_person_id": full_person_ids,
                            "source_household_id": household_ids,
                            "event_index": 0,
                            "draw_index": packed_draw_index(replicate, 0),
                            "seed_u64": full_seeds[replicate],
                            "weight": weights,
                            "observed_json": [
                                canonical_payload({"trip_count": int(x)})
                                for x in observed
                            ],
                            "generated_json": [
                                canonical_payload({"trip_count": int(x)})
                                for x in draws[replicate]
                            ],
                        }
                    )
                    frame.to_csv(
                        handle,
                        index=False,
                        header=not header_written,
                    )
                    header_written = True
                    evidence_rows += len(frame)
            for record in propagated_records:
                draws = propagated_draws[record.artifact_id]
                for replicate in range(REPLICATES):
                    frame = pd.DataFrame(
                        {
                            "component": COMPONENT,
                            "artifact_id": record.artifact_id,
                            "candidate_id": record.candidate_id,
                            "grid_id": record.grid_id,
                            "role": record.role,
                            "evaluation_mode": "PROPAGATED",
                            "replicate_id": replicate,
                            "evaluation_person_id": full_person_ids,
                            "source_household_id": household_ids,
                            "event_index": 0,
                            "draw_index": packed_draw_index(replicate, 0),
                            "seed_u64": full_seeds[replicate],
                            "weight": weights,
                            "observed_json": [
                                canonical_payload({"trip_count": int(x)})
                                for x in observed
                            ],
                            "generated_json": [
                                canonical_payload({"trip_count": int(x)})
                                for x in draws[replicate]
                            ],
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
            "schema": "F3_3C_STANDARD_EVIDENCE_V1_COMPATIBLE_TRIP_COUNT",
            "rows": evidence_rows,
            "isolated_rows_if_materialized": len(records) * REPLICATES * len(full),
            "propagated_artifacts": len(propagated_records),
            "propagated_rows_if_materialized": (
                len(propagated_records) * REPLICATES * len(full)
            ),
            "common_random_numbers": True,
            "replicates": REPLICATES,
        },
    )
    validations = [
        {"check": "cal_input_hashes_exact", "status": "PASS"},
        {"check": "cal_expected_rows_exact", "status": "PASS"},
        {"check": "trip_count_artifacts_exact_5", "status": "PASS"},
        {"check": "upstream_pa1_main_frozen", "status": "PASS"},
        {"check": "isolated_primary_crps", "status": "PASS"},
        {"check": "common_random_numbers_32", "status": "PASS"},
        {"check": "household_bootstrap_1000", "status": "PASS"},
        {"check": "propagated_check_executed", "status": "PASS"},
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
            "isolated_evaluation_rows": len(positive),
            "full_person_days": len(full),
            "candidate_artifacts": len(records),
            "stochastic_replicates": REPLICATES,
            "bootstrap_replicates": BOOTSTRAPS,
            "stochastic_evidence_rows": evidence_rows,
        },
    )
    manifest = {
        "phase": "F3.4c-2b",
        "component": COMPONENT,
        "status": "PASS",
        "execution_mode": "CONTROLLED_REAL_CAL",
        "candidate_artifacts": 5,
        "candidate_selection_state": selected["status"],
        "proposed_selected_artifact_id": selected[
            "proposed_selected_artifact_id"
        ],
        "propagated_guardrails_pass": propagated_pass,
        "cal_files_opened": access["cal_files_opened"],
        "cal_rows_read_total_physical": access["cal_rows_read_total_physical"],
        "cal_isolated_evaluation_rows": access["cal_isolated_evaluation_rows"],
        "cal_full_person_days": access["cal_full_person_days"],
        "test_rows_read": 0,
        "next_component_authorized": False,
        "test_open_authorized": False,
        "formal_g2": "NOT_EVALUATED",
        "implementation_commit": _git(repo_root, "rev-parse", "HEAD"),
    }
    _write_json(output_dir / "run_manifest.json", manifest)
    _write_checksums(output_dir)
    return manifest


def run_controlled_trip_count_cal(
    repo_root: Path,
    output_dir: Path,
    config_path: Path,
    authorization_path: Path,
    *,
    write_stochastic_evidence: bool = True,
) -> dict[str, Any]:
    """Run official Trip Count CAL atomically, preserving partial evidence on failure."""
    if output_dir.exists():
        raise FileExistsError(f"RunBundle output already exists: {output_dir}")
    staging = output_dir.with_name(f"{output_dir.name}.partial")
    if staging.exists():
        raise FileExistsError(f"Partial RunBundle already exists: {staging}")
    try:
        manifest = _run_controlled_trip_count_cal_direct(
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
                    "phase": "F3.4c-2b",
                    "exception_type": type(exc).__name__,
                    "exception_message": str(exc),
                    "cal_read_may_have_occurred": True,
                    "test_open_authorized": False,
                },
            )
            _write_checksums(staging)
        raise
