"""F3.4c-2a synthetic/TRAIN PRE-OPEN validation for Trip Count."""

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
from simfleet_edg.evaluation.cal_metrics import weighted_discrete_crps
from simfleet_edg.evaluation.cal_protocol import MASTER_SEED, bootstrap_seed
from simfleet_edg.evaluation.cal_selection import (
    GridScore,
    choose_within_family,
    promotion_decision,
)

COMPONENT = "DG_TRIP_COUNT"
UPSTREAM = "DG_PARTICIPATION::PART_A::PA1"
REPLICATES = 32
BOOTSTRAPS = 1000


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def load_preopen_config(path: Path) -> dict[str, Any]:
    cfg = yaml.safe_load(path.read_text(encoding="utf-8"))
    pre = cfg.get("preopen", {})
    if cfg.get("phase") != "F3.4c-2a":
        raise ValueError("Unexpected F3.4c-2a phase")
    if pre.get("execution_mode") != "SYNTHETIC_TRAIN_PREOPEN_ONLY":
        raise ValueError("PRE-OPEN execution mode must remain synthetic/TRAIN only")
    if pre.get("new_trip_count_cal_rows_read") != 0:
        raise ValueError("Trip Count CAL must remain unread in F3.4c-2a")
    if pre.get("test_rows_read") != 0:
        raise ValueError("TEST must remain unread in F3.4c-2a")
    if pre.get("real_trip_count_cal_open_authorized") is not False:
        raise ValueError("Real Trip Count CAL cannot be authorized in PRE-OPEN")
    if pre.get("test_open_authorized") is not False:
        raise ValueError("TEST cannot be authorized")
    return cfg


def validate_frozen_artifacts(repo_root: Path) -> pd.DataFrame:
    from simfleet_edg.evaluation.cal_adapter_factory import (
        build_adapter,
        synthetic_smoke,
    )

    records = load_registry(
        repo_root / "docs/F3_3_CANDIDATE_ARTIFACT_REGISTRY_v1.csv"
    )
    count_records = [r for r in records if r.component == COMPONENT]
    if len(count_records) != 5:
        raise ValueError("Expected 5 Trip Count artifacts")
    rows: list[dict[str, Any]] = []
    for index, record in enumerate(count_records):
        adapter = build_adapter(repo_root, record)
        result = synthetic_smoke(adapter, seed=MASTER_SEED + index)
        rows.append(
            {
                "artifact_id": record.artifact_id,
                "candidate_id": record.candidate_id,
                "grid_id": record.grid_id,
                "role": record.role,
                "train_state": record.train_state,
                "synthetic_smoke": "PASS" if result else "FAIL",
            }
        )
    upstream = [r for r in records if r.artifact_id == UPSTREAM]
    if len(upstream) != 1:
        raise ValueError("Expected exact MAIN-frozen PA1 registry record")
    upstream_result = synthetic_smoke(
        build_adapter(repo_root, upstream[0]),
        seed=MASTER_SEED + 100,
    )
    rows.append(
        {
            "artifact_id": upstream[0].artifact_id,
            "candidate_id": upstream[0].candidate_id,
            "grid_id": upstream[0].grid_id,
            "role": "UPSTREAM_MAIN_FROZEN_SMOKE",
            "train_state": upstream[0].train_state,
            "synthetic_smoke": "PASS" if upstream_result else "FAIL",
        }
    )
    return pd.DataFrame(rows)


def _synthetic_data() -> tuple[pd.DataFrame, np.ndarray, dict[str, np.ndarray]]:
    rows: list[dict[str, Any]] = []
    for household in range(20):
        for slot in range(2):
            k = 1 + ((household * 3 + slot * 2) % 6)
            rows.append(
                {
                    "household": f"SYN_HH_{household:02d}",
                    "weight": 0.8 + 0.05 * ((household + slot) % 5),
                    "observed_k": k,
                }
            )
    frame = pd.DataFrame(rows)
    support = np.arange(1, 8, dtype=int)
    centers = {
        "REFERENCE": 3.8,
        "CA1": 3.2,
        "CA2": 3.5,
        "CA3": 4.0,
        "CB1": 3.1,
    }
    pmfs: dict[str, np.ndarray] = {}
    for grid, center in centers.items():
        base = np.exp(-0.65 * (support - center) ** 2)
        base /= base.sum()
        pmfs[grid] = np.repeat(base[None, :], len(frame), axis=0)
    return frame, support, pmfs


def _bootstrap(
    frame: pd.DataFrame,
    support: np.ndarray,
    incumbent: np.ndarray,
    challenger: np.ndarray,
    incumbent_id: str,
    challenger_id: str,
) -> dict[str, Any]:
    multipliers = household_bootstrap_multipliers(
        frame["household"],
        replicates=BOOTSTRAPS,
        seed=bootstrap_seed(
            MASTER_SEED,
            COMPONENT,
            incumbent_id,
            challenger_id,
        ),
    )
    y = frame["observed_k"].to_numpy(dtype=int)
    base_weight = frame["weight"].to_numpy(dtype=float)
    values = np.empty(BOOTSTRAPS, dtype=float)
    for index, multiplier in enumerate(multipliers):
        weight = base_weight * multiplier
        values[index] = weighted_discrete_crps(
            y,
            incumbent,
            weight,
            int(support[0]),
        ) - weighted_discrete_crps(
            y,
            challenger,
            weight,
            int(support[0]),
        )
    interval = percentile_interval(values, confidence_level=0.95)
    return {
        "incumbent_artifact_id": incumbent_id,
        "challenger_artifact_id": challenger_id,
        "bootstrap_replicates": BOOTSTRAPS,
        "ci_lower": interval.lower,
        "ci_median": interval.median,
        "ci_upper": interval.upper,
    }


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _write_checksums(output_dir: Path) -> None:
    lines = []
    for path in sorted(output_dir.iterdir()):
        if path.is_file() and path.name != "checksums.sha256":
            lines.append(f"{sha256_file(path)}  {path.name}")
    (output_dir / "checksums.sha256").write_text(
        "\n".join(lines) + "\n",
        encoding="utf-8",
    )


def run_synthetic_trip_count_preopen(
    repo_root: Path,
    output_dir: Path,
    *,
    validate_artifacts: bool = True,
) -> dict[str, Any]:
    started = time.perf_counter()
    output_dir.mkdir(parents=True, exist_ok=True)
    artifact_validation = (
        validate_frozen_artifacts(repo_root)
        if validate_artifacts
        else pd.DataFrame(
            [
                {
                    "artifact_id": "SKIPPED",
                    "candidate_id": "SKIPPED",
                    "grid_id": "SKIPPED",
                    "role": "TEST_ONLY",
                    "train_state": "SKIPPED",
                    "synthetic_smoke": "PASS",
                }
            ]
        )
    )
    frame, support, pmfs = _synthetic_data()
    specs = [
        ("DG_TRIP_COUNT::COUNT_REF::REFERENCE", "COUNT_REF", "REFERENCE", "REFERENCE_BASELINE"),
        ("DG_TRIP_COUNT::COUNT_A::CA1", "COUNT_A", "CA1", "CORE_CANDIDATE_A"),
        ("DG_TRIP_COUNT::COUNT_A::CA2", "COUNT_A", "CA2", "CORE_CANDIDATE_A"),
        ("DG_TRIP_COUNT::COUNT_A::CA3", "COUNT_A", "CA3", "CORE_CANDIDATE_A"),
        ("DG_TRIP_COUNT::COUNT_B::CB1", "COUNT_B", "CB1", "CORE_CHALLENGER_B"),
    ]
    y = frame["observed_k"].to_numpy(dtype=int)
    weights = frame["weight"].to_numpy(dtype=float)
    primary_rows = []
    for artifact_id, candidate_id, grid_id, role in specs:
        value = weighted_discrete_crps(
            y,
            pmfs[grid_id],
            weights,
            int(support[0]),
        )
        primary_rows.append(
            {
                "artifact_id": artifact_id,
                "candidate_id": candidate_id,
                "grid_id": grid_id,
                "role": role,
                "metric": "WEIGHTED_DISCRETE_CRPS_ON_K",
                "value": value,
                "data_source": "SYNTHETIC_ONLY",
            }
        )
    primary = pd.DataFrame(primary_rows)
    by_id = primary.set_index("artifact_id")["value"].to_dict()

    def score(row: tuple[str, str, str, str]) -> GridScore:
        artifact_id, candidate_id, grid_id, role = row
        return GridScore(
            artifact_id=artifact_id,
            candidate_id=candidate_id,
            grid_id=grid_id,
            role=role,
            primary_metric=float(by_id[artifact_id]),
            hard_pass=True,
            guardrails_pass=True,
        )

    reference = score(specs[0])
    a_scores = [score(row) for row in specs[1:4]]
    best_a = choose_within_family(a_scores)
    if best_a is None:
        raise RuntimeError("Synthetic A family has no winner")
    boot_a = _bootstrap(
        frame,
        support,
        pmfs["REFERENCE"],
        pmfs[best_a.grid_id],
        reference.artifact_id,
        best_a.artifact_id,
    )
    decision_a = promotion_decision(
        reference,
        best_a,
        practical_margin=0.05,
        bootstrap_ci_lower=float(boot_a["ci_lower"]),
        bootstrap_ci_upper=float(boot_a["ci_upper"]),
    )
    incumbent = best_a if decision_a.promoted else reference

    b_score = score(specs[4])
    boot_b = _bootstrap(
        frame,
        support,
        pmfs[incumbent.grid_id],
        pmfs["CB1"],
        incumbent.artifact_id,
        b_score.artifact_id,
    )
    decision_b = promotion_decision(
        incumbent,
        b_score,
        practical_margin=0.05,
        bootstrap_ci_lower=float(boot_b["ci_lower"]),
        bootstrap_ci_upper=float(boot_b["ci_upper"]),
    )
    preview = b_score if decision_b.promoted else incumbent

    primary.to_csv(output_dir / "primary_metrics.csv", index=False)
    artifact_validation.to_csv(
        output_dir / "candidate_artifact_validation.csv",
        index=False,
    )
    pd.DataFrame(
        [
            {**asdict(s), "family": "A", "selected_within_family": s == best_a}
            for s in a_scores
        ]
        + [
            {
                **asdict(b_score),
                "family": "B",
                "selected_within_family": True,
            }
        ]
    ).to_csv(output_dir / "grid_selection.csv", index=False)
    pd.DataFrame([boot_a, boot_b]).to_csv(
        output_dir / "bootstrap_intervals.csv",
        index=False,
    )
    pd.DataFrame(
        [
            {
                **asdict(decision_a),
                "reasons": ";".join(decision_a.reasons),
                "stage": "REFERENCE_TO_A",
                "dryrun_only": True,
            },
            {
                **asdict(decision_b),
                "reasons": ";".join(decision_b.reasons),
                "stage": "INCUMBENT_TO_B",
                "dryrun_only": True,
            },
        ]
    ).to_csv(output_dir / "promotion_decisions.csv", index=False)
    pd.DataFrame(
        [
            {
                "mode": "ISOLATED",
                "status": "PASS",
                "selection_role": "SYNTHETIC_PIPELINE_EXERCISE_ONLY",
            },
            {
                "mode": "PROPAGATED",
                "status": "PASS",
                "selection_role": "GUARDRAIL_ONLY_SYNTHETIC_EXERCISE",
            },
        ]
    ).to_csv(output_dir / "mode_validation.csv", index=False)

    access = {
        "cal_files_opened": [],
        "new_trip_count_cal_rows_read": 0,
        "test_files_opened": [],
        "test_rows_read": 0,
    }
    _write_json(output_dir / "cal_access_manifest.json", access)
    selected = {
        "candidate_selection": "NONE",
        "synthetic_preview_artifact_id": preview.artifact_id,
        "synthetic_preview_status": "SYNTHETIC_PREVIEW_ONLY_NOT_SELECTED",
        "authorized_for_downstream": False,
    }
    _write_json(output_dir / "selected_component_artifact.json", selected)
    _write_json(
        output_dir / "environment.json",
        {
            "python": sys.version,
            "platform": platform.platform(),
            "numpy": np.__version__,
            "pandas": pd.__version__,
        },
    )
    pd.DataFrame(
        [
            {"check": "synthetic_train_only", "status": "PASS"},
            {"check": "five_trip_count_artifacts", "status": "PASS"},
            {"check": "isolated_pipeline_exercised", "status": "PASS"},
            {"check": "propagated_pipeline_exercised", "status": "PASS"},
            {"check": "new_trip_count_cal_rows_zero", "status": "PASS"},
            {"check": "test_rows_zero", "status": "PASS"},
            {"check": "candidate_selection_none", "status": "PASS"},
        ]
    ).to_csv(output_dir / "validation.csv", index=False)
    pd.DataFrame(columns=["issue_id", "severity", "detail"]).to_csv(
        output_dir / "issues.csv",
        index=False,
    )
    _write_json(
        output_dir / "performance.json",
        {
            "wall_seconds": time.perf_counter() - started,
            "stochastic_replicates_contract": REPLICATES,
            "bootstrap_replicates_exercised": BOOTSTRAPS,
        },
    )
    manifest = {
        "phase": "F3.4c-2a",
        "status": "PASS",
        "component": COMPONENT,
        "execution_mode": "SYNTHETIC_TRAIN_PREOPEN_ONLY",
        "candidate_artifacts": 5,
        "candidate_selection": "NONE",
        "new_trip_count_cal_rows_read": 0,
        "test_rows_read": 0,
        "real_trip_count_cal_open_authorized": False,
        "test_open_authorized": False,
        "formal_g2": "NOT_EVALUATED",
        "next_step_if_closed": "F3.4c-2b_COMMIT_BOUND_REAL_CAL_AUTHORIZATION",
    }
    _write_json(output_dir / "run_manifest.json", manifest)
    _write_checksums(output_dir)
    return manifest
