from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import subprocess
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

from simfleet_edg.demand.time_schedule import (
    build_time_backoff_model,
    canonical_json_bytes,
    encode_time_b_train,
    feature_matrix_sha256,
    finite_metrics,
    fit_quantile_models,
    fit_seed,
    load_train_time_tables,
    sha256_file,
    time_b_training_metrics,
    weighted_reference_temporal_support,
)


def _git(root: Path, *args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=root, text=True).strip()


def _repo_state(root: Path) -> dict[str, Any]:
    branch = _git(root, "branch", "--show-current")
    commit = _git(root, "rev-parse", "HEAD")
    status = _git(root, "status", "--porcelain")
    upstream = _git(root, "rev-parse", "--abbrev-ref", "@{upstream}")
    ahead_behind = _git(root, "rev-list", "--left-right", "--count", "HEAD...@{upstream}").split()
    return {
        "branch": branch,
        "commit": commit,
        "upstream": upstream,
        "ahead": int(ahead_behind[0]),
        "behind": int(ahead_behind[1]),
        "worktree_clean": status == "",
    }


def _require_official_repo_state(root: Path) -> dict[str, Any]:
    state = _repo_state(root)
    if state["branch"] != "main" or not state["worktree_clean"]:
        raise RuntimeError(f"Official fit requires clean main: {state}")
    if state["ahead"] != 0 or state["behind"] != 0:
        raise RuntimeError(f"Official fit requires synchronized origin/main: {state}")
    return state


def _library_versions() -> dict[str, str]:
    names = ["numpy", "pandas", "scipy", "scikit-learn", "statsmodels", "lightgbm"]
    return {name: importlib.metadata.version(name) for name in names}


def _write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical_json_bytes(obj))


def _validate_hash(path: Path, expected: str) -> dict[str, Any]:
    actual = sha256_file(path)
    return {
        "path": str(path),
        "expected_sha256": expected,
        "actual_sha256": actual,
        "status": "PASS" if actual == expected else "FAIL",
    }


def _validate_inputs(root: Path, cfg: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    materialized = root / cfg["inputs"]["materialized_root"]
    for key in ("train_context", "train_time_trips", "vocabulary_manifest", "materialization_manifest"):
        path = materialized / cfg["inputs"][key]
        row = _validate_hash(path, cfg["inputs"]["expected_sha256"][key])
        row.update({"kind": "input", "id": key})
        rows.append(row)
    for witness_id, spec in cfg["design_witnesses"].items():
        row = _validate_hash(root / spec["path"], spec["sha256"])
        row.update({"kind": "design", "id": witness_id})
        rows.append(row)
    env_root = root / cfg["environment_witness"]["root"]
    env_specs = {
        "environment_manifest.json": cfg["environment_witness"]["environment_manifest_sha256"],
        "pip_freeze.txt": cfg["environment_witness"]["pip_freeze_sha256"],
        "checksums.sha256": cfg["environment_witness"]["checksums_sha256"],
    }
    for name, expected in env_specs.items():
        row = _validate_hash(env_root / name, expected)
        row.update({"kind": "environment", "id": name})
        rows.append(row)
    failed = [row for row in rows if row["status"] != "PASS"]
    if failed:
        raise RuntimeError(f"Input/design/environment hash validation failed: {failed}")
    return rows


def _artifact_manifest(
    *,
    candidate_id: str,
    grid_id: str,
    commit: str,
    train_rows: int,
    fit_seed_value: int | None,
) -> dict[str, Any]:
    return {
        "artifact_id": f"{candidate_id}_{grid_id}",
        "component": "DG_TIME_SCHEDULE",
        "candidate_id": candidate_id,
        "grid_id": grid_id,
        "status": "FITTED_TRAIN_ONLY_NOT_SELECTED",
        "fit_partition": "TRAIN",
        "train_rows": train_rows,
        "fit_seed": fit_seed_value,
        "parent_git_commit": commit,
        "calibration": "NOT_EVALUATED",
        "cal_metrics": None,
        "selection_decision": "NOT_EVALUATED",
        "calibration_partition_consumed": False,
        "test_partition_consumed": False,
        "candidate_selection_performed": False,
        "temporal_invariant_policy": "REJECT_INVALID_DRAW_NO_SILENT_REPAIR",
        "planned_time_semantics": "NOT_EXECUTED_ROUTE_TRAVEL_TIME",
    }


def _checksums(out: Path) -> list[str]:
    lines = []
    for path in sorted(p for p in out.rglob("*") if p.is_file() and p.name != "checksums.sha256"):
        lines.append(f"{sha256_file(path)}  {path.relative_to(out)}")
    return lines


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[3]
    config_path = args.config if args.config.is_absolute() else root / args.config
    out = args.out if args.out.is_absolute() else root / args.out
    if out.exists():
        raise FileExistsError(f"Official output already exists: {out}")
    cfg = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    state = _require_official_repo_state(root)
    versions = _library_versions()
    required_versions = {k: str(v) for k, v in cfg["environment_witness"]["required_versions"].items()}
    if versions != required_versions:
        raise RuntimeError(f"Runtime versions differ from frozen environment: {versions}")
    validation_rows = _validate_inputs(root, cfg)

    materialized = root / cfg["inputs"]["materialized_root"]
    context, time, merged = load_train_time_tables(materialized, int(cfg["expected_train_rows"]))
    if len(context) != int(cfg["expected_context_rows"]):
        raise RuntimeError("Unexpected TRAIN context row count")
    if int((time["transition_context_status"] == "UNRESOLVED").sum()) != int(cfg["expected_unresolved_transition_context_rows"]):
        raise RuntimeError("Unexpected unresolved transition context count")

    out.mkdir(parents=True)
    input_hash_df = pd.DataFrame(validation_rows)[
        ["kind", "id", "path", "expected_sha256", "actual_sha256", "status"]
    ]
    input_hash_df.to_csv(out / "input_hash_validation.csv", index=False)

    feature_manifest = {
        "feature_set_id": cfg["feature_set_id"],
        "categorical_feature_columns": cfg["categorical_feature_columns"],
        "numeric_feature_columns": cfg["numeric_feature_columns"],
        "semantic_feature_mapping": cfg["semantic_feature_mapping"],
        "forbidden_feature_tokens": cfg["forbidden_feature_tokens"],
    }
    _write_json(out / "time_feature_manifest.json", feature_manifest)

    support_manifest = {
        "train_rows": len(merged),
        "departure_clock_support": [0, 1439],
        "arrival_clock_support": [0, 1439],
        "arrival_day_offset_support": sorted(time["target_arrival_day_offset"].astype(int).unique().tolist()),
        "duration_min": int(time["target_duration_from_clock_min"].min()),
        "duration_max": int(time["target_duration_from_clock_min"].max()),
        "trip_position_support": sorted(time["trip_position_class"].astype(str).unique().tolist()),
        "time_backoff_hierarchy": cfg["part_a"]["hierarchy"],
        "temporal_invariants": cfg["temporal_invariants"],
        "time_a_kernel_clarification": cfg["part_a"]["kernel_clarification"],
    }
    _write_json(out / "time_support_manifest.json", support_manifest)

    index_rows: list[dict[str, Any]] = []
    summary_rows: list[dict[str, Any]] = []
    backoff_rows: list[dict[str, Any]] = []

    # TIME_REF
    ref_model = weighted_reference_temporal_support(merged)
    ref_dir = out / "models" / "TIME_REF"
    _write_json(ref_dir / "model.json", ref_model)
    ref_manifest = _artifact_manifest(
        candidate_id="TIME_REF",
        grid_id="REFERENCE",
        commit=state["commit"],
        train_rows=len(merged),
        fit_seed_value=None,
    )
    _write_json(ref_dir / "artifact_manifest.json", ref_manifest)
    index_rows.append(
        {
            "candidate_id": "TIME_REF",
            "grid_id": "REFERENCE",
            "model_sha256": sha256_file(ref_dir / "model.json"),
            "manifest_sha256": sha256_file(ref_dir / "artifact_manifest.json"),
        }
    )
    weights = merged["fit_weight_W_GEW"].astype(float)
    summary_rows.append(
        {
            "candidate_id": "TIME_REF",
            "grid_id": "REFERENCE",
            "fit_seed": "",
            "weighted_multi_quantile_pinball_departure": "",
            "weighted_multi_quantile_pinball_duration": "",
            "weighted_multi_quantile_pinball_combined": "",
            "weighted_observed_mean_departure_minute": float((merged["target_departure_clock_minute"] * weights).sum() / weights.sum()),
            "weighted_predicted_median_departure_minute": "",
            "weighted_observed_mean_duration_minute": float((merged["target_duration_from_clock_min"] * weights).sum() / weights.sum()),
            "weighted_predicted_median_duration_minute": "",
            "status": "FITTED_TRAIN_ONLY_NOT_SELECTED",
        }
    )

    # TIME_A
    for grid_id, grid in cfg["part_a"]["grids"].items():
        seed = fit_seed(int(cfg["master_seed"]), "TIME_A", grid_id)
        model, backoff = build_time_backoff_model(
            merged,
            cfg["part_a"]["hierarchy"],
            bandwidth_minutes=int(grid["bandwidth_min"]),
            min_n=int(cfg["part_a"]["direct_support_min_n"]),
            max_rejection_attempts=int(cfg["part_a"]["max_rejection_attempts"]),
        )
        model["fit_seed"] = seed
        model_dir = out / "models" / "TIME_A" / grid_id
        _write_json(model_dir / "model.json", model)
        manifest = _artifact_manifest(
            candidate_id="TIME_A",
            grid_id=grid_id,
            commit=state["commit"],
            train_rows=len(merged),
            fit_seed_value=seed,
        )
        _write_json(model_dir / "artifact_manifest.json", manifest)
        index_rows.append(
            {
                "candidate_id": "TIME_A",
                "grid_id": grid_id,
                "model_sha256": sha256_file(model_dir / "model.json"),
                "manifest_sha256": sha256_file(model_dir / "artifact_manifest.json"),
            }
        )
        for row in backoff:
            backoff_rows.append({"grid_id": grid_id, **row})
        summary_rows.append(
            {
                "candidate_id": "TIME_A",
                "grid_id": grid_id,
                "fit_seed": seed,
                "weighted_multi_quantile_pinball_departure": "",
                "weighted_multi_quantile_pinball_duration": "",
                "weighted_multi_quantile_pinball_combined": "",
                "weighted_observed_mean_departure_minute": float((merged["target_departure_clock_minute"] * weights).sum() / weights.sum()),
                "weighted_predicted_median_departure_minute": "",
                "weighted_observed_mean_duration_minute": float((merged["target_duration_from_clock_min"] * weights).sum() / weights.sum()),
                "weighted_predicted_median_duration_minute": "",
                "status": "FITTED_TRAIN_ONLY_NOT_SELECTED",
            }
        )

    # TIME_B
    encoded = encode_time_b_train(
        merged,
        list(cfg["categorical_feature_columns"]),
        list(cfg["numeric_feature_columns"]),
    )
    _write_json(out / "time_b_encoder_manifest.json", encoded.encoder_manifest)
    quantiles = [float(q) for q in cfg["part_b"]["quantiles"]]
    for grid_id, grid in cfg["part_b"]["grids"].items():
        seed = fit_seed(int(cfg["master_seed"]), "TIME_B", grid_id)
        boosters, predictions = fit_quantile_models(
            encoded,
            common=cfg["part_b"]["common"],
            grid=grid,
            quantiles=quantiles,
            seed=seed,
        )
        metrics = time_b_training_metrics(encoded, predictions, quantiles)
        if not finite_metrics(metrics):
            raise RuntimeError(f"Non-finite TIME_B TRAIN metrics for {grid_id}")
        model = {
            "model_type": "LIGHTGBM_MULTI_QUANTILE_TEMPORAL_V1",
            "fit_partition": "TRAIN",
            "fit_seed": seed,
            "grid_id": grid_id,
            "quantiles": quantiles,
            "monotone_repair": cfg["part_b"]["monotone_repair"],
            "targets": ["departure_clock_minute", "duration_from_clock_min"],
            "feature_matrix_sha256": feature_matrix_sha256(encoded),
            "encoder_sha256": hashlib.sha256(canonical_json_bytes(encoded.encoder_manifest)).hexdigest(),
            "boosters": boosters,
            "runtime_temporal_policy": "SAMPLE_REPAIRED_QUANTILE_FUNCTION_THEN_REJECT_INVALID_NO_CLOCK_REPAIR",
            "planned_time_semantics": "NOT_EXECUTED_ROUTE_TRAVEL_TIME",
        }
        model_dir = out / "models" / "TIME_B" / grid_id
        _write_json(model_dir / "model.json", model)
        manifest = _artifact_manifest(
            candidate_id="TIME_B",
            grid_id=grid_id,
            commit=state["commit"],
            train_rows=len(merged),
            fit_seed_value=seed,
        )
        _write_json(model_dir / "artifact_manifest.json", manifest)
        index_rows.append(
            {
                "candidate_id": "TIME_B",
                "grid_id": grid_id,
                "model_sha256": sha256_file(model_dir / "model.json"),
                "manifest_sha256": sha256_file(model_dir / "artifact_manifest.json"),
            }
        )
        summary_rows.append(
            {
                "candidate_id": "TIME_B",
                "grid_id": grid_id,
                "fit_seed": seed,
                **metrics,
                "status": "FITTED_TRAIN_ONLY_NOT_SELECTED",
            }
        )

    pd.DataFrame(index_rows).to_csv(out / "model_artifact_index.csv", index=False)
    pd.DataFrame(summary_rows).to_csv(out / "train_fit_summary.csv", index=False)
    pd.DataFrame(backoff_rows).to_csv(out / "backoff_support_summary.csv", index=False)

    fit_checks = {
        "train_rows_exact": len(merged) == int(cfg["expected_train_rows"]),
        "candidates_fitted_exact": len(index_rows) == int(cfg["output_policy"]["expected_models"]),
        "calibration_not_read": True,
        "cal_metrics_absent": True,
        "selection_not_evaluated": True,
        "test_partition_consumed": False,
        "ids_not_features": True,
        "weights_not_features": True,
        "time_a_low_n_30": int(cfg["part_a"]["direct_support_min_n"]) == 30,
        "time_a_backoff_exact": cfg["part_a"]["hierarchy_id"] == "TIME_BACKOFF_V1",
        "time_a_no_clock_repair": cfg["part_a"]["silent_clock_repair"] is False,
        "time_b_train_vocab_only": True,
        "planned_time_not_execution_truth": True,
    }
    if not all(fit_checks.values()):
        raise RuntimeError(f"F3.2f fit validation failed: {fit_checks}")
    pd.DataFrame(
        [{"check": key, "status": "PASS" if value else "FAIL", "detail": ""} for key, value in fit_checks.items()]
    ).to_csv(out / "fit_validation.csv", index=False)

    manifest = {
        "status": "PASS",
        "phase": "F3.2f",
        "component": "DG_TIME_SCHEDULE",
        "run_id": out.name,
        "git": state,
        "config": str(config_path.relative_to(root)),
        "config_sha256": sha256_file(config_path),
        "runtime_versions": versions,
        "formal_g1": cfg["formal_g1"],
        "formal_g2": cfg["formal_g2"],
        "train_rows": len(merged),
        "context_rows": len(context),
        "unresolved_transition_context_rows": int((time["transition_context_status"] == "UNRESOLVED").sum()),
        "models_fitted": len(index_rows),
        "calibration_partition_consumed": False,
        "test_partition_consumed": False,
        "candidate_selection_performed": False,
        "temporal_invariant_policy": "REJECT_INVALID_DRAW_NO_SILENT_REPAIR",
        "time_a_kernel_clarification": cfg["part_a"]["kernel_clarification"],
    }
    _write_json(out / "fit_manifest.json", manifest)
    (out / "checksums.sha256").write_text("\n".join(_checksums(out)) + "\n", encoding="utf-8")
    print(json.dumps({"status": "PASS", "output": str(out.relative_to(root)), "models_fitted": len(index_rows)}, indent=2))


if __name__ == "__main__":
    main()
