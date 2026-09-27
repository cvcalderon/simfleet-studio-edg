"""F3.4b-1 Participation CAL runner synthetic dry-run.

This module intentionally contains no CAL/TEST reader. It validates the frozen
Participation artifacts using synthetic contexts and exercises the metric,
bootstrap, selection, CRN and RunBundle plumbing on a synthetic population.
"""

from __future__ import annotations

import hashlib
import json
import platform
import sys
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import yaml

from simfleet_edg.evaluation.cal_adapter_common import load_registry
from simfleet_edg.evaluation.cal_bootstrap import (
    household_bootstrap_multipliers,
    percentile_interval,
)
from simfleet_edg.evaluation.cal_metrics import weighted_bernoulli_logloss
from simfleet_edg.evaluation.cal_protocol import MASTER_SEED, bootstrap_seed, runtime_draw_seed
from simfleet_edg.evaluation.cal_selection import (
    GridScore,
    choose_within_family,
    promotion_decision,
)
from simfleet_edg.evaluation.participation_adapter import ParticipationAdapter

EXPECTED_COMPONENT = "DG_PARTICIPATION"
EXPECTED_REPLICATES = 32
EXPECTED_BOOTSTRAPS = 1000
DRYRUN_SCENARIO_ID = "F3_4B1_SYNTHETIC_DRYRUN_V1"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _synthetic_cases() -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for household_index in range(12):
        for person_slot in range(2):
            score = -1.25 + 0.24 * household_index + 0.55 * person_slot
            truth_probability = 1.0 / (1.0 + np.exp(-score))
            observed = int(((household_index * 7 + person_slot * 11) % 17) / 17 < truth_probability)
            rows.append(
                {
                    "source_household_id": f"SYN_HH_{household_index:02d}",
                    "evaluation_person_id": f"SYN_P_{household_index:02d}_{person_slot}",
                    "weight": 0.75 + 0.05 * ((household_index + person_slot) % 6),
                    "observed_trip_day": observed,
                    "truth_probability": truth_probability,
                    "signal": score,
                    "subgroup": "A" if household_index < 6 else "B",
                }
            )
    return pd.DataFrame(rows)


def _candidate_probability(frame: pd.DataFrame, grid_id: str) -> np.ndarray:
    signal = frame["signal"].to_numpy(dtype=float)
    specs: dict[str, tuple[float, float]] = {
        "REFERENCE": (0.00, 0.00),
        "PA1": (0.10, 0.90),
        "PA2": (0.00, 1.00),
        "PA3": (-0.08, 1.10),
        "PB1": (0.02, 1.04),
        "PB2": (-0.03, 1.08),
        "PB3": (0.12, 0.82),
        "PB4": (-0.12, 1.20),
    }
    if grid_id == "REFERENCE":
        return np.full(len(frame), 0.55, dtype=float)
    intercept, slope = specs[grid_id]
    return 1.0 / (1.0 + np.exp(-(intercept + slope * signal)))


def _candidate_rows(repo_root: Path, candidate_plan_path: Path) -> pd.DataFrame:
    plan = pd.read_csv(candidate_plan_path, dtype=str)
    rows = plan.loc[plan["component"] == EXPECTED_COMPONENT].copy()
    if len(rows) != 8:
        raise ValueError(f"Expected 8 Participation artifacts, got {len(rows)}")
    if set(rows["execution_stage"]) != {"FIRST_CONTROLLED_CAL_RUN"}:
        raise ValueError("Participation execution stage is not frozen as first CAL run")
    registry = pd.read_csv(repo_root / "docs/F3_3_CANDIDATE_ARTIFACT_REGISTRY_v1.csv", dtype=str)
    reg = registry.loc[registry["component"] == EXPECTED_COMPONENT].copy()
    if set(rows["artifact_id"]) != set(reg["artifact_id"]):
        raise ValueError("Participation candidate plan differs from frozen registry")
    return rows.sort_values(["complexity_rank", "candidate_id", "grid_id"]).reset_index(drop=True)


def validate_frozen_participation_artifacts(repo_root: Path) -> pd.DataFrame:
    records = [
        record
        for record in load_registry(repo_root / "docs/F3_3_CANDIDATE_ARTIFACT_REGISTRY_v1.csv")
        if record.component == EXPECTED_COMPONENT
    ]
    if len(records) != 8:
        raise ValueError("Expected exactly 8 frozen Participation records")
    rows: list[dict[str, Any]] = []
    for index, record in enumerate(records):
        adapter = ParticipationAdapter(repo_root, record)
        state: dict[str, Any] = {}
        for column, values in adapter.encoder.get("categories", {}).items():
            usable = [v for v in values if str(v) not in {"__MISSING_CONTEXT__", "__UNSEEN__"}]
            state[column] = usable[0] if usable else values[0]
        for column in adapter.encoder.get("numeric_columns", []):
            scaler = adapter.encoder.get("numeric_scalers", {}).get(column, {})
            state[column] = float(scaler.get("mean", 1.0))
        result = adapter.sample_one(pd.DataFrame([state]), seed=MASTER_SEED + index)
        rows.append(
            {
                "artifact_id": record.artifact_id,
                "candidate_id": record.candidate_id,
                "grid_id": record.grid_id,
                "role": record.role,
                "train_state": record.train_state,
                "model_sha256": record.model_sha256,
                "manifest_sha256": record.manifest_sha256,
                "synthetic_smoke": "PASS" if result else "FAIL",
            }
        )
    return pd.DataFrame(rows)


def _share_error(frame: pd.DataFrame, generated: np.ndarray, row_weights: np.ndarray | None = None) -> float:
    weights = frame["weight"].to_numpy(dtype=float)
    if row_weights is not None:
        weights = weights * np.asarray(row_weights, dtype=float)
    observed_share = float(np.average(frame["observed_trip_day"], weights=weights))
    generated_share = float(np.average(generated, weights=weights))
    return abs(generated_share - observed_share)


def _subgroup_max_share_error(frame: pd.DataFrame, generated: np.ndarray) -> float:
    out: list[float] = []
    for subgroup in sorted(frame["subgroup"].unique()):
        mask = frame["subgroup"].to_numpy() == subgroup
        out.append(_share_error(frame.loc[mask].reset_index(drop=True), generated[mask]))
    return max(out)


def _stochastic_guardrails(frame: pd.DataFrame, probability: np.ndarray) -> tuple[float, float, int]:
    share_errors: list[float] = []
    subgroup_errors: list[float] = []
    seed_count = 0
    for replicate_id in range(EXPECTED_REPLICATES):
        draws = np.empty(len(frame), dtype=int)
        for row_index, person_id in enumerate(frame["evaluation_person_id"]):
            seed = runtime_draw_seed(
                MASTER_SEED,
                DRYRUN_SCENARIO_ID,
                str(person_id),
                EXPECTED_COMPONENT,
                replicate_id,
            )
            seed_count += 1
            draws[row_index] = int(np.random.default_rng(seed).random() < probability[row_index])
        share_errors.append(_share_error(frame, draws))
        subgroup_errors.append(_subgroup_max_share_error(frame, draws))
    return float(np.mean(share_errors)), float(np.mean(subgroup_errors)), seed_count


def _bootstrap_primary(
    frame: pd.DataFrame,
    incumbent_probability: np.ndarray,
    challenger_probability: np.ndarray,
    *,
    incumbent_id: str,
    challenger_id: str,
) -> dict[str, float | int]:
    multipliers = household_bootstrap_multipliers(
        frame["source_household_id"],
        replicates=EXPECTED_BOOTSTRAPS,
        seed=bootstrap_seed(MASTER_SEED, EXPECTED_COMPONENT, incumbent_id, challenger_id),
    )
    y = frame["observed_trip_day"].to_numpy(dtype=int)
    base_weight = frame["weight"].to_numpy(dtype=float)
    differences = np.empty(EXPECTED_BOOTSTRAPS, dtype=float)
    for index, multiplier in enumerate(multipliers):
        weight = base_weight * multiplier
        if float(weight.sum()) <= 0:
            raise ValueError("Synthetic bootstrap removed all rows")
        incumbent = weighted_bernoulli_logloss(y, incumbent_probability, weight)
        challenger = weighted_bernoulli_logloss(y, challenger_probability, weight)
        differences[index] = incumbent - challenger
    interval = percentile_interval(differences, confidence_level=0.95)
    return {
        "bootstrap_replicates": EXPECTED_BOOTSTRAPS,
        "ci_lower": interval.lower,
        "ci_median": interval.median,
        "ci_upper": interval.upper,
    }


def _write_csv(path: Path, rows: list[dict[str, Any]] | pd.DataFrame) -> None:
    frame = rows if isinstance(rows, pd.DataFrame) else pd.DataFrame(rows)
    frame.to_csv(path, index=False)


def _json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _checksums(output_dir: Path) -> None:
    target = output_dir / "checksums.sha256"
    lines: list[str] = []
    for path in sorted(output_dir.iterdir()):
        if path.is_file() and path.name != target.name:
            lines.append(f"{sha256_file(path)}  {path.name}")
    target.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run_synthetic_participation_dryrun(
    repo_root: Path,
    output_dir: Path,
    *,
    validate_frozen_artifacts: bool = True,
) -> dict[str, Any]:
    started = time.perf_counter()
    repo_root = repo_root.resolve()
    output_dir = output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    plan_path = repo_root / "docs/F3_4A_CANDIDATE_EXECUTION_PLAN_v1.csv"
    candidates = _candidate_rows(repo_root, plan_path)
    synthetic = _synthetic_cases()

    artifact_validation = (
        validate_frozen_participation_artifacts(repo_root)
        if validate_frozen_artifacts
        else pd.DataFrame(
            {
                "artifact_id": candidates["artifact_id"],
                "candidate_id": candidates["candidate_id"],
                "grid_id": candidates["grid_id"],
                "role": candidates["role"],
                "train_state": candidates["train_state_required"],
                "synthetic_smoke": "SKIPPED_BY_TEST_HARNESS",
            }
        )
    )

    primary_rows: list[dict[str, Any]] = []
    guardrail_rows: list[dict[str, Any]] = []
    probabilities: dict[str, np.ndarray] = {}
    score_objects: list[GridScore] = []

    for row in candidates.to_dict(orient="records"):
        grid_id = str(row["grid_id"])
        probability = _candidate_probability(synthetic, grid_id)
        probabilities[str(row["artifact_id"])] = probability
        primary = weighted_bernoulli_logloss(
            synthetic["observed_trip_day"], probability, synthetic["weight"]
        )
        share_error, subgroup_error, seed_count = _stochastic_guardrails(synthetic, probability)
        guardrails_pass = bool(share_error <= 0.35 and subgroup_error <= 0.50)
        primary_rows.append(
            {
                "artifact_id": row["artifact_id"],
                "candidate_id": row["candidate_id"],
                "grid_id": grid_id,
                "role": row["role"],
                "metric": "WEIGHTED_BERNOULLI_LOG_LOSS",
                "value": primary,
                "data_source": "SYNTHETIC_ONLY",
            }
        )
        guardrail_rows.extend(
            [
                {
                    "artifact_id": row["artifact_id"],
                    "guardrail": "M2-PART-01_SYNTHETIC_SHARE_ERROR",
                    "value": share_error,
                    "replicates": EXPECTED_REPLICATES,
                    "pass": guardrails_pass,
                },
                {
                    "artifact_id": row["artifact_id"],
                    "guardrail": "M2-COND-01_SYNTHETIC_MAX_SUBGROUP_SHARE_ERROR",
                    "value": subgroup_error,
                    "replicates": EXPECTED_REPLICATES,
                    "pass": guardrails_pass,
                },
            ]
        )
        score_objects.append(
            GridScore(
                artifact_id=str(row["artifact_id"]),
                candidate_id=str(row["candidate_id"]),
                grid_id=grid_id,
                role=str(row["role"]),
                primary_metric=primary,
                hard_pass=True,
                guardrails_pass=guardrails_pass,
            )
        )
        if seed_count != EXPECTED_REPLICATES * len(synthetic):
            raise AssertionError("CRN dry-run seed coverage incomplete")

    ref = next(score for score in score_objects if score.role == "REFERENCE_BASELINE")
    best_a = choose_within_family(score for score in score_objects if score.role == "CORE_CANDIDATE_A")
    best_b = choose_within_family(score for score in score_objects if score.role == "CORE_CHALLENGER_B")
    if best_a is None or best_b is None:
        raise ValueError("Synthetic dry-run requires valid A and B family representatives")

    bootstrap_rows: list[dict[str, Any]] = []
    promotion_rows: list[dict[str, Any]] = []
    incumbent = ref
    for challenger, stage in ((best_a, "REFERENCE_TO_A"), (best_b, "INCUMBENT_TO_B")):
        boot = _bootstrap_primary(
            synthetic,
            probabilities[incumbent.artifact_id],
            probabilities[challenger.artifact_id],
            incumbent_id=incumbent.artifact_id,
            challenger_id=challenger.artifact_id,
        )
        decision = promotion_decision(
            incumbent,
            challenger,
            practical_margin=0.005,
            bootstrap_ci_lower=float(boot["ci_lower"]),
            bootstrap_ci_upper=float(boot["ci_upper"]),
        )
        bootstrap_rows.append(
            {
                "stage": stage,
                "incumbent_artifact_id": incumbent.artifact_id,
                "challenger_artifact_id": challenger.artifact_id,
                **boot,
            }
        )
        promotion_rows.append({"stage": stage, **asdict(decision), "dryrun_only": True})
        if decision.promoted:
            incumbent = challenger

    grid_rows = []
    for family, selected in (("REFERENCE_BASELINE", ref), ("CORE_CANDIDATE_A", best_a), ("CORE_CHALLENGER_B", best_b)):
        grid_rows.append(
            {
                "family": family,
                "synthetic_preview_artifact_id": selected.artifact_id,
                "synthetic_preview_grid_id": selected.grid_id,
                "candidate_selection": "NONE",
            }
        )

    input_hash_rows = [
        {
            "input": "docs/F3_3_CANDIDATE_ARTIFACT_REGISTRY_v1.csv",
            "sha256": sha256_file(repo_root / "docs/F3_3_CANDIDATE_ARTIFACT_REGISTRY_v1.csv"),
            "read_type": "METADATA_ONLY",
        },
        {
            "input": "docs/F3_4A_CANDIDATE_EXECUTION_PLAN_v1.csv",
            "sha256": sha256_file(plan_path),
            "read_type": "METADATA_ONLY",
        },
    ]

    _write_csv(output_dir / "input_hash_validation.csv", input_hash_rows)
    _write_csv(output_dir / "candidate_artifact_validation.csv", artifact_validation)
    _write_csv(output_dir / "primary_metrics.csv", primary_rows)
    _write_csv(output_dir / "guardrails.csv", guardrail_rows)
    _write_csv(output_dir / "bootstrap_intervals.csv", bootstrap_rows)
    _write_csv(output_dir / "grid_selection.csv", grid_rows)
    _write_csv(output_dir / "promotion_decisions.csv", promotion_rows)
    _write_csv(
        output_dir / "validation.csv",
        [
            {"check": "synthetic_only", "status": "PASS"},
            {"check": "cal_rows_read_zero", "status": "PASS"},
            {"check": "test_rows_read_zero", "status": "PASS"},
            {"check": "candidate_selection_none", "status": "PASS"},
            {"check": "participation_artifacts_exact_8", "status": "PASS"},
            {"check": "stochastic_replicates_32", "status": "PASS"},
            {"check": "household_bootstrap_1000", "status": "PASS"},
        ],
    )
    _write_csv(output_dir / "issues.csv", pd.DataFrame(columns=["issue_id", "severity", "detail"]))

    f34a_config = repo_root / "configs/f3/f3_4a_controlled_cal_execution_contract_v1.yaml"
    (output_dir / "execution_contract_snapshot.yaml").write_bytes(f34a_config.read_bytes())
    _json(
        output_dir / "environment.json",
        {
            "python": sys.version,
            "platform": platform.platform(),
            "numpy": np.__version__,
            "pandas": pd.__version__,
        },
    )
    _json(
        output_dir / "cal_access_manifest.json",
        {
            "mode": "SYNTHETIC_DRYRUN_ONLY",
            "cal_partition": "UNOPENED",
            "cal_files_opened": [],
            "cal_rows_read": 0,
            "test_partition": "SEALED",
            "test_files_opened": [],
            "test_rows_read": 0,
        },
    )
    _json(
        output_dir / "part_b_calibration_decision.json",
        {
            "status": "NOT_RUN_IN_F3_4B1_DRYRUN",
            "reason": "PART_B calibration occurs only in controlled real CAL after family/grid selection",
            "candidate_selection": "NONE",
        },
    )
    _json(
        output_dir / "selected_component_artifact.json",
        {
            "status": "SYNTHETIC_PREVIEW_ONLY_NOT_SELECTED",
            "synthetic_preview_artifact_id": incumbent.artifact_id,
            "candidate_selection": "NONE",
            "authorized_for_downstream": False,
        },
    )
    elapsed = time.perf_counter() - started
    _json(
        output_dir / "performance.json",
        {
            "wall_seconds": elapsed,
            "synthetic_person_rows": len(synthetic),
            "candidate_artifacts": 8,
            "stochastic_replicates": EXPECTED_REPLICATES,
            "bootstrap_replicates": EXPECTED_BOOTSTRAPS,
        },
    )
    manifest = {
        "phase": "F3.4b-1",
        "component": EXPECTED_COMPONENT,
        "status": "PASS",
        "execution_mode": "SYNTHETIC_DRYRUN_ONLY",
        "data_source": "SYNTHETIC_ONLY",
        "candidate_artifacts": 8,
        "candidate_selection": "NONE",
        "synthetic_preview_artifact_id": incumbent.artifact_id,
        "cal_rows_read": 0,
        "test_rows_read": 0,
        "test_open_authorized": False,
        "formal_g2": "NOT_EVALUATED",
        "next_step_if_closed": "F3.4b-2_CONTROLLED_REAL_CAL_DG_PARTICIPATION",
    }
    _json(output_dir / "run_manifest.json", manifest)
    _checksums(output_dir)
    return manifest


def load_dryrun_config(path: Path) -> dict[str, Any]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if payload["phase"] != "F3.4b-1":
        raise ValueError("Unexpected dry-run phase")
    if payload["execution_mode"] != "SYNTHETIC_DRYRUN_ONLY":
        raise ValueError("F3.4b-1 may only run in synthetic dry-run mode")
    if payload["cal_rows_read"] != 0 or payload["test_rows_read"] != 0:
        raise ValueError("F3.4b-1 freezes CAL/TEST row reads to zero")
    return payload
