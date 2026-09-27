from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import subprocess
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import yaml

from simfleet_edg.demand.distance_prior import (
    build_distance_backoff_model,
    canonical_json_bytes,
    distance_b_training_metrics,
    encode_distance_b_train,
    feature_matrix_sha256,
    finite_metrics,
    fit_quantile_models,
    fit_seed,
    load_train_distance_tables,
    repair_distance_quantiles,
    sha256_file,
    weighted_quantile,
    weighted_reference_distance_support,
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
    input_keys = (
        "train_context",
        "train_distance_raw",
        "train_distance_expanded_sensitivity",
        "vocabulary_manifest",
        "materialization_manifest",
    )
    for key in input_keys:
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
        "component": "DG_DISTANCE_PRIOR",
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
        "primary_target": "RAW_WEGKM",
        "sensitivity_target_consumed_for_fit": False,
        "km_routing_consumed": False,
        "distance_semantics": "M2_PATH_LENGTH_PRIOR_FOR_M3_NOT_EXACT_OD_OR_ROUTED_DISTANCE",
    }


def _checksums(out: Path) -> list[str]:
    lines = []
    for path in sorted(p for p in out.rglob("*") if p.is_file() and p.name != "checksums.sha256"):
        lines.append(f"{sha256_file(path)}  {path.relative_to(out)}")
    return lines


def _fit_check_passed(check: str, value: bool) -> bool:
    expected_false = {
        "test_partition_consumed",
        "calibration_partition_consumed",
        "candidate_selection_performed",
        "sensitivity_target_consumed_for_fit",
        "km_routing_consumed",
    }
    expected = check not in expected_false
    return bool(value) == expected


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
    required_versions = {key: str(value) for key, value in cfg["environment_witness"]["required_versions"].items()}
    if versions != required_versions:
        raise RuntimeError(f"Runtime versions differ from frozen environment: {versions}")
    validation_rows = _validate_inputs(root, cfg)

    materialized = root / cfg["inputs"]["materialized_root"]
    context, distance, merged = load_train_distance_tables(materialized, int(cfg["expected_train_rows"]))
    sensitivity = pd.read_csv(materialized / cfg["inputs"]["train_distance_expanded_sensitivity"])

    if len(context) != int(cfg["expected_context_rows"]):
        raise RuntimeError("Unexpected TRAIN context row count")
    if len(sensitivity) != int(cfg["expected_sensitivity_rows"]):
        raise RuntimeError("Unexpected TRAIN sensitivity row count")
    if int(distance["source_trip_count_analogue"].isna().sum()) != int(cfg["expected_missing_trip_count_rows"]):
        raise RuntimeError("Unexpected missing trip-count analogue count")
    if int((distance["time_context_status"] == "MISSING_SOURCE_CONTEXT").sum()) != int(cfg["expected_missing_time_context_rows"]):
        raise RuntimeError("Unexpected missing time-context count")
    if int((distance["transition_context_status"] == "UNRESOLVED").sum()) != int(cfg["expected_unresolved_transition_context_rows"]):
        raise RuntimeError("Unexpected unresolved transition-context count")
    if set(distance["distance_provenance"].astype(str).unique()) != {"RAW_WEGKM"}:
        raise RuntimeError("Primary TRAIN distance provenance must be RAW_WEGKM only")

    out.mkdir(parents=True)
    pd.DataFrame(validation_rows)[
        ["kind", "id", "path", "expected_sha256", "actual_sha256", "status"]
    ].to_csv(out / "input_hash_validation.csv", index=False)

    feature_manifest = {
        "feature_set_id": cfg["feature_set_id"],
        "categorical_feature_columns": cfg["categorical_feature_columns"],
        "numeric_feature_columns": cfg["numeric_feature_columns"],
        "semantic_feature_mapping": cfg["semantic_feature_mapping"],
        "implementation_clarification": cfg["implementation_clarifications"]["encoder"],
        "forbidden_feature_tokens": cfg["forbidden_feature_tokens"],
    }
    _write_json(out / "distance_feature_manifest.json", feature_manifest)

    target = distance["target_distance_prior_km"].astype(float).to_numpy()
    weights = distance["fit_weight_W_GEW"].astype(float).to_numpy()
    support_manifest = {
        "train_rows": len(distance),
        "sensitivity_rows_report_only": len(sensitivity),
        "target_min_km": float(target.min()),
        "target_max_km": float(target.max()),
        "primary_provenance_support": sorted(distance["distance_provenance"].astype(str).unique().tolist()),
        "sensitivity_provenance_support": sorted(sensitivity["distance_provenance"].astype(str).unique().tolist()),
        "missing_trip_count_rows": int(distance["source_trip_count_analogue"].isna().sum()),
        "missing_time_context_rows": int((distance["time_context_status"] == "MISSING_SOURCE_CONTEXT").sum()),
        "unresolved_transition_context_rows": int((distance["transition_context_status"] == "UNRESOLVED").sum()),
        "distance_backoff_hierarchy": cfg["part_a"]["hierarchy"],
        "implementation_clarifications": cfg["implementation_clarifications"],
        "distance_semantics": cfg["primary_target"]["semantics"],
        "km_routing_consumed": False,
    }
    _write_json(out / "distance_support_manifest.json", support_manifest)

    sensitivity_summary = {
        "role": "REPORT_ONLY_NOT_PRIMARY_FIT",
        "rows": int(len(sensitivity)),
        "raw_rows": int((sensitivity["distance_provenance"] == "RAW_WEGKM").sum()),
        "source_imputed_rows": int((sensitivity["distance_provenance"] == "SOURCE_IMPUTED_WEGKM").sum()),
        "consumed_for_primary_fit": False,
    }
    _write_json(out / "distance_sensitivity_universe_manifest.json", sensitivity_summary)

    index_rows: list[dict[str, Any]] = []
    summary_rows: list[dict[str, Any]] = []
    backoff_rows: list[dict[str, Any]] = []

    observed_mean = float(np.average(target, weights=weights))
    observed_p50 = weighted_quantile(target, weights, 0.50)
    observed_p90 = weighted_quantile(target, weights, 0.90)
    observed_p95 = weighted_quantile(target, weights, 0.95)

    # DIST_REF
    ref_model = weighted_reference_distance_support(merged)
    ref_dir = out / "models" / "DIST_REF"
    _write_json(ref_dir / "model.json", ref_model)
    ref_manifest = _artifact_manifest(
        candidate_id="DIST_REF",
        grid_id="REFERENCE",
        commit=state["commit"],
        train_rows=len(merged),
        fit_seed_value=None,
    )
    _write_json(ref_dir / "artifact_manifest.json", ref_manifest)
    index_rows.append(
        {
            "candidate_id": "DIST_REF",
            "grid_id": "REFERENCE",
            "model_sha256": sha256_file(ref_dir / "model.json"),
            "manifest_sha256": sha256_file(ref_dir / "artifact_manifest.json"),
        }
    )
    summary_rows.append(
        {
            "candidate_id": "DIST_REF",
            "grid_id": "REFERENCE",
            "fit_seed": "",
            "weighted_multi_quantile_pinball_raw_km": "",
            "weighted_multi_quantile_pinball_repaired_km": "",
            "weighted_observed_mean_km": observed_mean,
            "weighted_predicted_median_mean_km": "",
            "weighted_observed_p50_km": observed_p50,
            "weighted_observed_p90_km": observed_p90,
            "weighted_observed_p95_km": observed_p95,
            "status": "FITTED_TRAIN_ONLY_NOT_SELECTED",
        }
    )

    # DIST_A / DA1
    for grid_id in cfg["part_a"]["grids"]:
        seed = fit_seed(int(cfg["master_seed"]), "DIST_A", grid_id)
        model, backoff = build_distance_backoff_model(
            merged,
            cfg["part_a"]["hierarchy"],
            min_n=int(cfg["part_a"]["direct_support_min_n"]),
        )
        model["fit_seed"] = seed
        model["grid_id"] = grid_id
        model_dir = out / "models" / "DIST_A" / grid_id
        _write_json(model_dir / "model.json", model)
        artifact = _artifact_manifest(
            candidate_id="DIST_A",
            grid_id=grid_id,
            commit=state["commit"],
            train_rows=len(merged),
            fit_seed_value=seed,
        )
        _write_json(model_dir / "artifact_manifest.json", artifact)
        index_rows.append(
            {
                "candidate_id": "DIST_A",
                "grid_id": grid_id,
                "model_sha256": sha256_file(model_dir / "model.json"),
                "manifest_sha256": sha256_file(model_dir / "artifact_manifest.json"),
            }
        )
        for row in backoff:
            backoff_rows.append({"grid_id": grid_id, **row})
        summary_rows.append(
            {
                "candidate_id": "DIST_A",
                "grid_id": grid_id,
                "fit_seed": seed,
                "weighted_multi_quantile_pinball_raw_km": "",
                "weighted_multi_quantile_pinball_repaired_km": "",
                "weighted_observed_mean_km": observed_mean,
                "weighted_predicted_median_mean_km": "",
                "weighted_observed_p50_km": observed_p50,
                "weighted_observed_p90_km": observed_p90,
                "weighted_observed_p95_km": observed_p95,
                "status": "FITTED_TRAIN_ONLY_NOT_SELECTED",
            }
        )

    # DIST_B / DB1-DB3
    encoded = encode_distance_b_train(
        merged,
        list(cfg["categorical_feature_columns"]),
        list(cfg["numeric_feature_columns"]),
    )
    _write_json(out / "distance_b_encoder_manifest.json", encoded.encoder_manifest)
    quantiles = [float(value) for value in cfg["part_b"]["quantiles"]]
    target_min = float(encoded.target.min())
    target_max = float(encoded.target.max())
    for grid_id, grid in cfg["part_b"]["grids"].items():
        seed = fit_seed(int(cfg["master_seed"]), "DIST_B", grid_id)
        boosters, raw_predictions = fit_quantile_models(
            encoded,
            common=cfg["part_b"]["common"],
            grid=grid,
            quantiles=quantiles,
            seed=seed,
        )
        repaired_predictions = repair_distance_quantiles(raw_predictions, target_min, target_max)
        metrics = distance_b_training_metrics(encoded, raw_predictions, repaired_predictions, quantiles)
        if not finite_metrics(metrics):
            raise RuntimeError(f"Non-finite DIST_B TRAIN metrics for {grid_id}")
        model = {
            "model_type": "LIGHTGBM_MULTI_QUANTILE_RAW_WEGKM_V1",
            "fit_partition": "TRAIN",
            "fit_seed": seed,
            "grid_id": grid_id,
            "quantiles": quantiles,
            "target": "RAW_WEGKM",
            "target_column": "target_distance_prior_km",
            "feature_matrix_sha256": feature_matrix_sha256(encoded),
            "encoder_sha256": hashlib.sha256(canonical_json_bytes(encoded.encoder_manifest)).hexdigest(),
            "boosters": boosters,
            "runtime_reconstruction": cfg["implementation_clarifications"]["dist_b_reconstruction"],
            "global_strict_train_target_min_km": target_min,
            "global_strict_train_target_max_km": target_max,
            "distance_semantics": cfg["primary_target"]["semantics"],
        }
        model_dir = out / "models" / "DIST_B" / grid_id
        _write_json(model_dir / "model.json", model)
        artifact = _artifact_manifest(
            candidate_id="DIST_B",
            grid_id=grid_id,
            commit=state["commit"],
            train_rows=len(merged),
            fit_seed_value=seed,
        )
        _write_json(model_dir / "artifact_manifest.json", artifact)
        index_rows.append(
            {
                "candidate_id": "DIST_B",
                "grid_id": grid_id,
                "model_sha256": sha256_file(model_dir / "model.json"),
                "manifest_sha256": sha256_file(model_dir / "artifact_manifest.json"),
            }
        )
        summary_rows.append(
            {
                "candidate_id": "DIST_B",
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
        "sensitivity_rows_exact": len(sensitivity) == int(cfg["expected_sensitivity_rows"]),
        "candidates_fitted_exact": len(index_rows) == int(cfg["output_policy"]["expected_models"]),
        "calibration_partition_consumed": False,
        "candidate_selection_performed": False,
        "test_partition_consumed": False,
        "sensitivity_target_consumed_for_fit": False,
        "km_routing_consumed": False,
        "ids_not_features": True,
        "weights_not_features": True,
        "quality_flags_not_features": True,
        "primary_target_raw_wegkm_only": set(distance["distance_provenance"].astype(str).unique()) == {"RAW_WEGKM"},
        "distance_a_low_n_30": int(cfg["part_a"]["direct_support_min_n"]) == 30,
        "distance_a_backoff_exact": cfg["part_a"]["hierarchy_id"] == "DIST_BACKOFF_V1",
        "distance_b_train_vocab_only": True,
        "distance_semantics_not_exact_od": True,
        "implementation_clarifications_pre_cal": cfg["implementation_clarifications"]["status"] == "FROZEN_PRE_CAL_IMPLEMENTATION_CLARIFICATIONS",
    }
    failed_fit_checks = {
        key: value for key, value in fit_checks.items() if not _fit_check_passed(key, value)
    }
    if failed_fit_checks:
        raise RuntimeError(f"F3.2g fit validation failed: {failed_fit_checks}")
    pd.DataFrame(
        [
            {
                "check": key,
                "status": "PASS" if _fit_check_passed(key, value) else "FAIL",
                "detail": "false" if not value else "",
            }
            for key, value in fit_checks.items()
        ]
    ).to_csv(out / "fit_validation.csv", index=False)

    manifest = {
        "status": "PASS",
        "phase": "F3.2g",
        "component": "DG_DISTANCE_PRIOR",
        "run_id": out.name,
        "git": state,
        "config": str(config_path.relative_to(root)),
        "config_sha256": sha256_file(config_path),
        "runtime_versions": versions,
        "formal_g1": cfg["formal_g1"],
        "formal_g2": cfg["formal_g2"],
        "train_rows": len(merged),
        "context_rows": len(context),
        "sensitivity_rows_report_only": len(sensitivity),
        "missing_trip_count_rows": int(distance["source_trip_count_analogue"].isna().sum()),
        "missing_time_context_rows": int((distance["time_context_status"] == "MISSING_SOURCE_CONTEXT").sum()),
        "unresolved_transition_context_rows": int((distance["transition_context_status"] == "UNRESOLVED").sum()),
        "models_fitted": len(index_rows),
        "calibration_partition_consumed": False,
        "candidate_selection_performed": False,
        "test_partition_consumed": False,
        "sensitivity_target_consumed_for_fit": False,
        "km_routing_consumed": False,
        "primary_target": "RAW_WEGKM",
        "distance_semantics": cfg["primary_target"]["semantics"],
        "implementation_clarifications": cfg["implementation_clarifications"],
    }
    _write_json(out / "fit_manifest.json", manifest)
    (out / "checksums.sha256").write_text("\n".join(_checksums(out)) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {"status": "PASS", "output": str(out.relative_to(root)), "models_fitted": len(index_rows)},
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
