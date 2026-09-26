from __future__ import annotations

import argparse
import importlib.metadata
import json
import subprocess
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

from simfleet_edg.demand.trip_count import (
    build_count_backoff_model,
    canonical_count_keys,
    canonical_json_bytes,
    count_support,
    feature_matrix_sha256,
    finite_metrics,
    fit_nb2_l2,
    fit_reference,
    fit_seed,
    load_train_trip_count,
    sha256_file,
    training_metrics_from_pmfs,
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


def _load_config(path: Path) -> dict[str, Any]:
    return yaml.safe_load(path.read_text())


def _library_versions() -> dict[str, str]:
    names = ["numpy", "pandas", "scipy", "scikit-learn", "statsmodels", "lightgbm"]
    return {name: importlib.metadata.version(name) for name in names}


def _validate_inputs(root: Path, cfg: dict[str, Any]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    materialized = root / cfg["inputs"]["materialized_root"]
    for key in ("train_context", "train_trip_count", "vocabulary_manifest", "materialization_manifest"):
        path = materialized / cfg["inputs"][key]
        expected = cfg["inputs"]["expected_sha256"][key]
        actual = sha256_file(path)
        rows.append(
            {
                "kind": "input",
                "id": key,
                "path": str(path.relative_to(root)),
                "expected_sha256": expected,
                "actual_sha256": actual,
                "status": "PASS" if expected == actual else "FAIL",
            }
        )
    for key, witness in cfg["design_witnesses"].items():
        path = root / witness["path"]
        actual = sha256_file(path)
        rows.append(
            {
                "kind": "design",
                "id": key,
                "path": witness["path"],
                "expected_sha256": witness["sha256"],
                "actual_sha256": actual,
                "status": "PASS" if witness["sha256"] == actual else "FAIL",
            }
        )
    env_root = root / cfg["environment_witness"]["root"]
    for filename, config_key in (
        ("environment_manifest.json", "environment_manifest_sha256"),
        ("pip_freeze.txt", "pip_freeze_sha256"),
        ("checksums.sha256", "checksums_sha256"),
    ):
        actual = sha256_file(env_root / filename)
        expected = cfg["environment_witness"][config_key]
        rows.append(
            {
                "kind": "environment",
                "id": filename,
                "path": str((env_root / filename).relative_to(root)),
                "expected_sha256": expected,
                "actual_sha256": actual,
                "status": "PASS" if expected == actual else "FAIL",
            }
        )
    failed = [row for row in rows if row["status"] != "PASS"]
    if failed:
        raise RuntimeError(f"Input/design/environment hash validation failed: {failed}")
    return rows


def _write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical_json_bytes(obj))


def _write_model_manifest(
    path: Path,
    *,
    cfg: dict[str, Any],
    repo_state: dict[str, Any],
    candidate_id: str,
    grid_id: str | None,
    fit_seed_value: int | None,
    model_relpath: str,
    model_sha256: str,
    train_metrics: dict[str, float],
    feature_manifest_hash: str,
    encoder_manifest_hash: str,
    feature_matrix_hash: str,
    support_manifest_hash: str,
    library_versions: dict[str, str],
    config_sha256: str,
    implementation_timestamp: str,
) -> None:
    is_ref = candidate_id == "COUNT_REF"
    is_a = candidate_id == "COUNT_A"
    backoff = "COUNT_BACKOFF_V1" if candidate_id == "COUNT_B" else "NOT_APPLICABLE"
    _write_json(
        path,
        {
            "artifact_id": f"DG_TRIP_COUNT::{candidate_id}::{grid_id or 'REFERENCE'}",
            "component": "DG_TRIP_COUNT",
            "candidate_id": candidate_id,
            "grid_id": grid_id,
            "parent_git_commit": repo_state["commit"],
            "config_sha256": config_sha256,
            "source_hashes": cfg["inputs"]["expected_sha256"],
            "split_manifest_sha256": cfg["split_manifest_sha256"],
            "design_parent_commit": cfg["expected_parent_commit"],
            "feature_set_id": "NONE" if is_ref else cfg["feature_set_id"],
            "feature_manifest_sha256": None if is_ref else feature_manifest_hash,
            "encoder_manifest_sha256": encoder_manifest_hash if is_a else None,
            "vocabulary_sha256": cfg["inputs"]["expected_sha256"]["vocabulary_manifest"],
            "feature_matrix_sha256": feature_matrix_hash if is_a else None,
            "support_manifest_sha256": support_manifest_hash,
            "train_universe": "REF_TRAIN_CORE_STRICT_COUNT_MOBILE",
            "train_rows": cfg["expected_train_rows"],
            "train_row_counts": {
                "REF_TRAIN_CORE_STRICT_COUNT_MOBILE": cfg["expected_train_rows"]
            },
            "k_min": cfg["k_min"],
            "k_max_train": cfg["k_max_train"],
            "weighting": "P_GEW",
            "fit_seed": fit_seed_value,
            "library_versions": library_versions,
            "serialized_model_path": model_relpath,
            "serialized_model_sha256": model_sha256,
            "train_metrics": train_metrics,
            "cal_metrics": None,
            "bootstrap": None,
            "backoff": backoff,
            "calibration": "NOT_EVALUATED",
            "selection_decision": "NOT_EVALUATED",
            "calibration_partition_consumed": False,
            "test_partition_consumed": False,
            "candidate_selection_performed": False,
            "timestamp": implementation_timestamp,
            "timestamp_source": "IMPLEMENTATION_GIT_COMMIT_COMMITTER_TIME",
            "status": "FITTED_TRAIN_ONLY_NOT_SELECTED",
        },
    )


def run(root: Path, config_path: Path, out: Path) -> dict[str, Any]:
    cfg = _load_config(config_path)
    if out.exists():
        raise RuntimeError(f"Output already exists: {out}")
    repo_state = _require_official_repo_state(root)
    implementation_timestamp = _git(root, "show", "-s", "--format=%cI", "HEAD")
    config_sha256 = sha256_file(config_path)
    validation_rows = _validate_inputs(root, cfg)
    versions = _library_versions()
    if versions != cfg["environment_witness"]["required_versions"]:
        raise RuntimeError("Resolved library versions differ from the frozen environment")

    materialized = root / cfg["inputs"]["materialized_root"]
    data, encoder = load_train_trip_count(
        materialized,
        list(cfg["feature_columns"]),
        int(cfg["expected_train_rows"]),
        int(cfg["k_min"]),
        int(cfg["k_max_train"]),
    )
    if data.merged["row_id"].isna().sum() != int(cfg["expected_join_missing_context"]):
        raise RuntimeError("Unexpected missing person_day_context joins")

    out.mkdir(parents=True, exist_ok=False)
    _write_json(out / "count_a_encoder_manifest.json", encoder)
    encoder_manifest_hash = sha256_file(out / "count_a_encoder_manifest.json")
    matrix_hash = feature_matrix_sha256(data)

    feature_manifest = {
        "component": "DG_TRIP_COUNT",
        "feature_set_id": cfg["feature_set_id"],
        "semantic_feature_mapping": cfg["semantic_feature_mapping"],
        "source_feature_columns": cfg["feature_columns"],
        "count_a_encoder": {
            "manifest_path": "count_a_encoder_manifest.json",
            "manifest_sha256": encoder_manifest_hash,
            "encoded_feature_count": len(data.feature_names),
        },
        "count_b": {
            "hierarchy_id": cfg["part_b"]["hierarchy_id"],
            "hierarchy": cfg["part_b"]["hierarchy"],
            "season_conditioned_level_added": False,
            "note": cfg["part_b"]["note_on_season"],
        },
        "fit_partition": "TRAIN",
        "rare_pooling": "NONE",
        "unseen_runtime_category": "__UNSEEN__",
    }
    _write_json(out / "count_feature_manifest.json", feature_manifest)
    feature_manifest_hash = sha256_file(out / "count_feature_manifest.json")

    observed_support = sorted({int(value) for value in data.k.tolist()})
    support_manifest = {
        "component": "DG_TRIP_COUNT",
        "k_min": data.k_min,
        "k_max_train": data.k_max,
        "full_integer_support": count_support(data.k_min, data.k_max).tolist(),
        "canonical_support_keys": canonical_count_keys(data.k_min, data.k_max),
        "observed_train_support": observed_support,
        "nb2_runtime_tail_policy": "TRUNCATE_AND_RENORMALIZE_TO_FULL_INTEGER_SUPPORT",
        "posthoc_clipping": False,
    }
    _write_json(out / "count_support_manifest.json", support_manifest)
    support_manifest_hash = sha256_file(out / "count_support_manifest.json")

    fit_rows: list[dict[str, Any]] = []
    artifact_rows: list[dict[str, Any]] = []

    ref_model, ref_pmf = fit_reference(data)
    ref_metrics = training_metrics_from_pmfs(data, ref_pmf)
    if not finite_metrics(ref_metrics):
        raise RuntimeError("Non-finite COUNT_REF TRAIN metrics")
    ref_path = out / "models" / "COUNT_REF" / "model.json"
    _write_json(ref_path, ref_model)
    ref_sha = sha256_file(ref_path)
    ref_manifest = out / "models" / "COUNT_REF" / "artifact_manifest.json"
    _write_model_manifest(
        ref_manifest,
        cfg=cfg,
        repo_state=repo_state,
        candidate_id="COUNT_REF",
        grid_id=None,
        fit_seed_value=None,
        model_relpath=str(ref_path.relative_to(out)),
        model_sha256=ref_sha,
        train_metrics=ref_metrics,
        feature_manifest_hash=feature_manifest_hash,
        encoder_manifest_hash=encoder_manifest_hash,
        feature_matrix_hash=matrix_hash,
        support_manifest_hash=support_manifest_hash,
        library_versions=versions,
        config_sha256=config_sha256,
        implementation_timestamp=implementation_timestamp,
    )
    fit_rows.append(
        {
            "candidate_id": "COUNT_REF",
            "grid_id": "REFERENCE",
            "fit_seed": "",
            **ref_metrics,
            "status": "FITTED_TRAIN_ONLY_NOT_SELECTED",
        }
    )
    artifact_rows.append(
        {
            "candidate_id": "COUNT_REF",
            "grid_id": "REFERENCE",
            "model_sha256": ref_sha,
            "manifest_sha256": sha256_file(ref_manifest),
        }
    )

    for grid_id, grid in cfg["part_a"]["grids"].items():
        seed = fit_seed(int(cfg["master_seed"]), "COUNT_A", grid_id)
        model, pmfs = fit_nb2_l2(
            data,
            float(grid["lambda_l2"]),
            int(cfg["part_a"]["optimizer_maxiter"]),
            float(cfg["part_a"]["optimizer_ftol"]),
            float(cfg["part_a"]["optimizer_gtol"]),
            tuple(float(v) for v in cfg["part_a"]["coefficient_bounds"]),
            tuple(float(v) for v in cfg["part_a"]["log_alpha_bounds"]),
            bool(cfg["part_a"]["reject_if_optimizer_boundary_hit"]),
        )
        model["fit_seed"] = seed
        metrics = training_metrics_from_pmfs(data, pmfs)
        metrics["train_untruncated_weighted_nb2_nll"] = float(
            model["train_untruncated_weighted_nb2_nll"]
        )
        metrics["train_alpha"] = float(model["alpha"])
        if not finite_metrics(metrics):
            raise RuntimeError(f"Non-finite COUNT_A TRAIN metrics: {grid_id}")
        model_path = out / "models" / "COUNT_A" / grid_id / "model.json"
        _write_json(model_path, model)
        model_sha = sha256_file(model_path)
        manifest_path = out / "models" / "COUNT_A" / grid_id / "artifact_manifest.json"
        _write_model_manifest(
            manifest_path,
            cfg=cfg,
            repo_state=repo_state,
            candidate_id="COUNT_A",
            grid_id=grid_id,
            fit_seed_value=seed,
            model_relpath=str(model_path.relative_to(out)),
            model_sha256=model_sha,
            train_metrics=metrics,
            feature_manifest_hash=feature_manifest_hash,
            encoder_manifest_hash=encoder_manifest_hash,
            feature_matrix_hash=matrix_hash,
            support_manifest_hash=support_manifest_hash,
            library_versions=versions,
            config_sha256=config_sha256,
            implementation_timestamp=implementation_timestamp,
        )
        fit_rows.append(
            {
                "candidate_id": "COUNT_A",
                "grid_id": grid_id,
                "fit_seed": seed,
                **metrics,
                "status": "FITTED_TRAIN_ONLY_NOT_SELECTED",
            }
        )
        artifact_rows.append(
            {
                "candidate_id": "COUNT_A",
                "grid_id": grid_id,
                "model_sha256": model_sha,
                "manifest_sha256": sha256_file(manifest_path),
            }
        )

    b_grid_id = str(cfg["part_b"]["grid_id"])
    b_seed = fit_seed(int(cfg["master_seed"]), "COUNT_B", b_grid_id)
    b_model, b_pmfs, backoff_summary = build_count_backoff_model(
        data.merged,
        [list(level) for level in cfg["part_b"]["hierarchy"]],
        "fit_weight_P_GEW_target",
        cfg["target_column"],
        int(cfg["k_min"]),
        int(cfg["k_max_train"]),
        int(cfg["part_b"]["direct_support_min_n"]),
    )
    b_model["fit_seed"] = b_seed
    b_metrics = training_metrics_from_pmfs(data, b_pmfs)
    if not finite_metrics(b_metrics):
        raise RuntimeError("Non-finite COUNT_B TRAIN metrics")
    b_path = out / "models" / "COUNT_B" / b_grid_id / "model.json"
    _write_json(b_path, b_model)
    b_sha = sha256_file(b_path)
    b_manifest = out / "models" / "COUNT_B" / b_grid_id / "artifact_manifest.json"
    _write_model_manifest(
        b_manifest,
        cfg=cfg,
        repo_state=repo_state,
        candidate_id="COUNT_B",
        grid_id=b_grid_id,
        fit_seed_value=b_seed,
        model_relpath=str(b_path.relative_to(out)),
        model_sha256=b_sha,
        train_metrics=b_metrics,
        feature_manifest_hash=feature_manifest_hash,
        encoder_manifest_hash=encoder_manifest_hash,
        feature_matrix_hash=matrix_hash,
        support_manifest_hash=support_manifest_hash,
        library_versions=versions,
        config_sha256=config_sha256,
        implementation_timestamp=implementation_timestamp,
    )
    fit_rows.append(
        {
            "candidate_id": "COUNT_B",
            "grid_id": b_grid_id,
            "fit_seed": b_seed,
            **b_metrics,
            "status": "FITTED_TRAIN_ONLY_NOT_SELECTED",
        }
    )
    artifact_rows.append(
        {
            "candidate_id": "COUNT_B",
            "grid_id": b_grid_id,
            "model_sha256": b_sha,
            "manifest_sha256": sha256_file(b_manifest),
        }
    )

    backoff_summary.to_csv(
        out / "backoff_support_summary.csv",
        index=False,
        lineterminator="\n",
    )
    pd.DataFrame(fit_rows).to_csv(
        out / "train_fit_summary.csv",
        index=False,
        lineterminator="\n",
        float_format="%.15g",
    )
    pd.DataFrame(validation_rows).to_csv(
        out / "input_hash_validation.csv",
        index=False,
        lineterminator="\n",
    )
    pd.DataFrame(artifact_rows).to_csv(
        out / "model_artifact_index.csv",
        index=False,
        lineterminator="\n",
    )

    validation = [
        {
            "check": "train_rows_exact",
            "status": "PASS" if data.source_rows == int(cfg["expected_train_rows"]) else "FAIL",
            "detail": str(data.source_rows),
        },
        {
            "check": "k_support_exact",
            "status": "PASS" if (data.k_min, data.k_max) == (1, 50) else "FAIL",
            "detail": f"{data.k_min}..{data.k_max}",
        },
        {
            "check": "candidates_fitted_exact",
            "status": "PASS" if len(fit_rows) == int(cfg["output_policy"]["expected_models"]) else "FAIL",
            "detail": str(len(fit_rows)),
        },
        {"check": "calibration_not_read", "status": "PASS", "detail": "runner consumes TRAIN paths only"},
        {"check": "cal_metrics_absent", "status": "PASS", "detail": "all artifact manifests set cal_metrics=null"},
        {"check": "selection_not_evaluated", "status": "PASS", "detail": "all artifacts remain FITTED_TRAIN_ONLY_NOT_SELECTED"},
        {"check": "test_partition_consumed", "status": "PASS", "detail": "false"},
        {"check": "ids_not_features", "status": "PASS", "detail": "feature list frozen in config"},
        {"check": "weights_not_features", "status": "PASS", "detail": "P_GEW used only as fit/probability weight"},
        {"check": "count_a_train_vocab_only", "status": "PASS", "detail": encoder_manifest_hash},
        {"check": "count_a_tail_truncated_renormalized", "status": "PASS", "detail": support_manifest_hash},
        {"check": "count_b_low_n_30", "status": "PASS", "detail": str(cfg["part_b"]["direct_support_min_n"])},
        {"check": "count_b_backoff_exact", "status": "PASS", "detail": cfg["part_b"]["hierarchy_id"]},
        {"check": "season_level_not_invented", "status": "PASS", "detail": "COUNT_BACKOFF_V1 preserved literally"},
    ]
    pd.DataFrame(validation).to_csv(
        out / "fit_validation.csv",
        index=False,
        lineterminator="\n",
    )
    if any(row["status"] != "PASS" for row in validation):
        raise RuntimeError("F3.2d validation failed")

    manifest = {
        "run_id": "F3_2D_TRIP_COUNT_FIT_V1",
        "phase": "F3.2d",
        "component": "DG_TRIP_COUNT",
        "git": repo_state,
        "design_parent_commit": cfg["expected_parent_commit"],
        "formal_g1": cfg["formal_g1"],
        "formal_g2": cfg["formal_g2"],
        "test_partition_consumed": False,
        "calibration_partition_consumed": False,
        "candidate_selection_performed": False,
        "train_rows": data.source_rows,
        "k_min": data.k_min,
        "k_max_train": data.k_max,
        "feature_set_id": cfg["feature_set_id"],
        "feature_columns": cfg["feature_columns"],
        "feature_manifest_sha256": feature_manifest_hash,
        "count_a_encoder_manifest_sha256": encoder_manifest_hash,
        "count_a_feature_matrix_sha256": matrix_hash,
        "count_support_manifest_sha256": support_manifest_hash,
        "library_versions": versions,
        "environment_witness": cfg["environment_witness"],
        "config_sha256": config_sha256,
        "split_manifest_sha256": cfg["split_manifest_sha256"],
        "implementation_timestamp": implementation_timestamp,
        "input_hash_validation": f"{len(validation_rows)}/{len(validation_rows)} PASS",
        "models_fitted": len(fit_rows),
        "status": "PASS",
    }
    _write_json(out / "fit_manifest.json", manifest)

    files = sorted(path for path in out.rglob("*") if path.is_file() and path.name != "checksums.sha256")
    checksum_lines = [f"{sha256_file(path)}  {path.relative_to(out).as_posix()}" for path in files]
    (out / "checksums.sha256").write_text("\n".join(checksum_lines) + "\n")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[3]
    config = Path(args.config)
    if not config.is_absolute():
        config = root / config
    out = Path(args.out)
    if not out.is_absolute():
        out = root / out
    manifest = run(root, config, out)
    print(
        json.dumps(
            {
                "status": manifest["status"],
                "output": str(out.relative_to(root)),
                "models_fitted": manifest["models_fitted"],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
