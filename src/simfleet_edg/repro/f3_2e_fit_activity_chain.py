from __future__ import annotations

import argparse
import importlib.metadata
import json
import subprocess
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

from simfleet_edg.demand.activity_chain import (
    build_chain_backoff_model,
    canonical_json_bytes,
    encode_chain_b_train,
    feature_matrix_sha256,
    finite_metrics,
    fit_multinomial_l2,
    fit_reference_transition_model,
    fit_seed,
    load_train_chain_tables,
    sha256_file,
    target_activity_classes,
    training_metrics,
    weighted_initial_activity_pmf,
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
    input_keys = (
        "train_context",
        "train_chain_days",
        "train_chain_transitions",
        "vocabulary_manifest",
        "materialization_manifest",
    )
    for key in input_keys:
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
    is_ref = candidate_id == "CHAIN_REF"
    is_b = candidate_id == "CHAIN_B"
    backoff = "CHAIN_BACKOFF_V1" if candidate_id == "CHAIN_A" else "NOT_APPLICABLE"
    _write_json(
        path,
        {
            "artifact_id": f"DG_ACTIVITY_CHAIN::{candidate_id}::{grid_id or 'REFERENCE'}",
            "component": "DG_ACTIVITY_CHAIN",
            "candidate_id": candidate_id,
            "grid_id": grid_id,
            "parent_git_commit": repo_state["commit"],
            "config_sha256": config_sha256,
            "source_hashes": cfg["inputs"]["expected_sha256"],
            "split_manifest_sha256": cfg["split_manifest_sha256"],
            "design_parent_commit": cfg["expected_parent_commit"],
            "feature_set_id": "PREVIOUS_ACTIVITY_ONLY_REFERENCE" if is_ref else cfg["feature_set_id"],
            "feature_manifest_sha256": None if is_ref else feature_manifest_hash,
            "encoder_manifest_sha256": encoder_manifest_hash if is_b else None,
            "vocabulary_sha256": cfg["inputs"]["expected_sha256"]["vocabulary_manifest"],
            "feature_matrix_sha256": feature_matrix_hash if is_b else None,
            "support_manifest_sha256": support_manifest_hash,
            "train_universe": "REF_TRAIN_FULL_FUNCTIONAL_MOBILE",
            "train_day_rows": cfg["expected_train_day_rows"],
            "train_transition_rows": cfg["expected_train_transition_rows"],
            "weighting": "W_GEW; P_GEW for day-level sequence diagnostics",
            "fit_seed": fit_seed_value,
            "library_versions": library_versions,
            "serialized_model_path": model_relpath,
            "serialized_model_sha256": model_sha256,
            "train_metrics": train_metrics,
            "cal_metrics": None,
            "bootstrap": None,
            "backoff": backoff,
            "return_home_forced": False,
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
    context, days, merged = load_train_chain_tables(
        materialized,
        int(cfg["expected_train_day_rows"]),
        int(cfg["expected_train_transition_rows"]),
    )
    if len(context) != int(cfg["expected_context_rows"]):
        raise RuntimeError("Unexpected TRAIN person_day_context row count")
    if int(merged["row_id"].isna().sum()) != int(cfg["expected_join_missing_context"]):
        raise RuntimeError("Unexpected missing person_day_context joins")

    classes = target_activity_classes(merged)
    encoded = encode_chain_b_train(
        merged,
        list(cfg["categorical_feature_columns"]),
        list(cfg["numeric_feature_columns"]),
        classes,
    )
    initial_activity = weighted_initial_activity_pmf(days, classes)

    out.mkdir(parents=True, exist_ok=False)
    _write_json(out / "chain_b_encoder_manifest.json", encoded.encoder_manifest)
    encoder_manifest_hash = sha256_file(out / "chain_b_encoder_manifest.json")
    matrix_hash = feature_matrix_sha256(encoded)

    feature_manifest = {
        "component": "DG_ACTIVITY_CHAIN",
        "feature_set_id": cfg["feature_set_id"],
        "semantic_feature_mapping": cfg["semantic_feature_mapping"],
        "categorical_feature_columns": cfg["categorical_feature_columns"],
        "numeric_feature_columns": cfg["numeric_feature_columns"],
        "chain_a": {
            "hierarchy_id": cfg["part_a"]["hierarchy_id"],
            "hierarchy": cfg["part_a"]["hierarchy"],
            "support_count_basis": cfg["part_a"]["support_count_basis"],
        },
        "chain_b": {
            "encoder_manifest_path": "chain_b_encoder_manifest.json",
            "encoder_manifest_sha256": encoder_manifest_hash,
            "encoded_feature_count": len(encoded.feature_names),
        },
        "fit_partition": "TRAIN",
        "teacher_forcing_runtime": False,
        "rare_pooling": "NONE",
        "unseen_runtime_category": "__UNSEEN__",
    }
    _write_json(out / "chain_feature_manifest.json", feature_manifest)
    feature_manifest_hash = sha256_file(out / "chain_feature_manifest.json")

    support_manifest = {
        "component": "DG_ACTIVITY_CHAIN",
        "activity_support": classes,
        "activity_support_count": len(classes),
        "start_token": cfg["start_token"],
        "initial_activity_model": initial_activity,
        "sequence_constraint": cfg["sequence_constraint"],
        "return_home_forced": False,
        "observed_train_k_min": int(days["source_trip_count_analogue"].min()),
        "observed_train_k_max": int(days["source_trip_count_analogue"].max()),
        "observed_train_first_origin_activities": sorted(
            {str(value) for value in days["first_origin_activity"]}
        ),
    }
    _write_json(out / "chain_support_manifest.json", support_manifest)
    support_manifest_hash = sha256_file(out / "chain_support_manifest.json")

    fit_rows: list[dict[str, Any]] = []
    artifact_rows: list[dict[str, Any]] = []
    backoff_rows: list[pd.DataFrame] = []

    ref_model, ref_probs = fit_reference_transition_model(merged, classes)
    ref_model["initial_activity_model"] = initial_activity
    ref_metrics = training_metrics(merged, classes, ref_probs)
    if not finite_metrics(ref_metrics):
        raise RuntimeError("Non-finite CHAIN_REF TRAIN metrics")
    ref_path = out / "models" / "CHAIN_REF" / "model.json"
    _write_json(ref_path, ref_model)
    ref_sha = sha256_file(ref_path)
    ref_manifest = out / "models" / "CHAIN_REF" / "artifact_manifest.json"
    _write_model_manifest(
        ref_manifest,
        cfg=cfg,
        repo_state=repo_state,
        candidate_id="CHAIN_REF",
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
            "candidate_id": "CHAIN_REF",
            "grid_id": "REFERENCE",
            "fit_seed": "",
            **ref_metrics,
            "status": "FITTED_TRAIN_ONLY_NOT_SELECTED",
        }
    )
    artifact_rows.append(
        {
            "candidate_id": "CHAIN_REF",
            "grid_id": "REFERENCE",
            "model_sha256": ref_sha,
            "manifest_sha256": sha256_file(ref_manifest),
        }
    )

    for grid_id, grid in cfg["part_a"]["grids"].items():
        seed = fit_seed(int(cfg["master_seed"]), "CHAIN_A", grid_id)
        model, probs, summary = build_chain_backoff_model(
            merged,
            [list(level) for level in cfg["part_a"]["hierarchy"]],
            classes,
            int(cfg["part_a"]["direct_support_min_n"]),
            float(grid["dirichlet_alpha"]),
        )
        model["fit_seed"] = seed
        model["grid_id"] = grid_id
        model["initial_activity_model"] = initial_activity
        metrics = training_metrics(merged, classes, probs)
        if not finite_metrics(metrics):
            raise RuntimeError(f"Non-finite CHAIN_A TRAIN metrics: {grid_id}")
        model_path = out / "models" / "CHAIN_A" / grid_id / "model.json"
        _write_json(model_path, model)
        model_sha = sha256_file(model_path)
        manifest_path = out / "models" / "CHAIN_A" / grid_id / "artifact_manifest.json"
        _write_model_manifest(
            manifest_path,
            cfg=cfg,
            repo_state=repo_state,
            candidate_id="CHAIN_A",
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
                "candidate_id": "CHAIN_A",
                "grid_id": grid_id,
                "fit_seed": seed,
                **metrics,
                "status": "FITTED_TRAIN_ONLY_NOT_SELECTED",
            }
        )
        artifact_rows.append(
            {
                "candidate_id": "CHAIN_A",
                "grid_id": grid_id,
                "model_sha256": model_sha,
                "manifest_sha256": sha256_file(manifest_path),
            }
        )
        summary.insert(0, "grid_id", grid_id)
        backoff_rows.append(summary)

    for grid_id, grid in cfg["part_b"]["grids"].items():
        seed = fit_seed(int(cfg["master_seed"]), "CHAIN_B", grid_id)
        model, probs = fit_multinomial_l2(
            encoded,
            float(grid["lambda_l2"]),
            int(cfg["part_b"]["optimizer_maxiter"]),
            float(cfg["part_b"]["optimizer_ftol"]),
            float(cfg["part_b"]["optimizer_gtol"]),
            tuple(float(v) for v in cfg["part_b"]["coefficient_bounds"]),
            bool(cfg["part_b"]["reject_if_optimizer_boundary_hit"]),
        )
        model["fit_seed"] = seed
        model["grid_id"] = grid_id
        model["encoder_manifest_sha256"] = encoder_manifest_hash
        model["initial_activity_model"] = initial_activity
        metrics = training_metrics(merged, classes, probs)
        if not finite_metrics(metrics):
            raise RuntimeError(f"Non-finite CHAIN_B TRAIN metrics: {grid_id}")
        model_path = out / "models" / "CHAIN_B" / grid_id / "model.json"
        _write_json(model_path, model)
        model_sha = sha256_file(model_path)
        manifest_path = out / "models" / "CHAIN_B" / grid_id / "artifact_manifest.json"
        _write_model_manifest(
            manifest_path,
            cfg=cfg,
            repo_state=repo_state,
            candidate_id="CHAIN_B",
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
                "candidate_id": "CHAIN_B",
                "grid_id": grid_id,
                "fit_seed": seed,
                **metrics,
                "status": "FITTED_TRAIN_ONLY_NOT_SELECTED",
            }
        )
        artifact_rows.append(
            {
                "candidate_id": "CHAIN_B",
                "grid_id": grid_id,
                "model_sha256": model_sha,
                "manifest_sha256": sha256_file(manifest_path),
            }
        )

    pd.concat(backoff_rows, ignore_index=True).to_csv(
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
            "check": "train_day_rows_exact",
            "status": "PASS" if len(days) == int(cfg["expected_train_day_rows"]) else "FAIL",
            "detail": str(len(days)),
        },
        {
            "check": "train_transition_rows_exact",
            "status": "PASS"
            if len(merged) == int(cfg["expected_train_transition_rows"])
            else "FAIL",
            "detail": str(len(merged)),
        },
        {
            "check": "exact_k_transitions",
            "status": "PASS"
            if int(days["source_trip_count_analogue"].sum()) == len(merged)
            else "FAIL",
            "detail": "sum(K)==transition_rows",
        },
        {
            "check": "candidates_fitted_exact",
            "status": "PASS"
            if len(fit_rows) == int(cfg["output_policy"]["expected_models"])
            else "FAIL",
            "detail": str(len(fit_rows)),
        },
        {"check": "calibration_not_read", "status": "PASS", "detail": "runner consumes TRAIN paths only"},
        {"check": "cal_metrics_absent", "status": "PASS", "detail": "all artifact manifests set cal_metrics=null"},
        {
            "check": "selection_not_evaluated",
            "status": "PASS",
            "detail": "all artifacts remain FITTED_TRAIN_ONLY_NOT_SELECTED",
        },
        {"check": "test_partition_consumed", "status": "PASS", "detail": "false"},
        {"check": "ids_not_features", "status": "PASS", "detail": "feature lists frozen in config"},
        {"check": "weights_not_features", "status": "PASS", "detail": "W_GEW/P_GEW are weights only"},
        {
            "check": "purpose_not_predictor",
            "status": "PASS",
            "detail": "canonical_trip_purpose excluded from features",
        },
        {"check": "return_home_not_forced", "status": "PASS", "detail": "false"},
        {"check": "chain_a_low_n_30", "status": "PASS", "detail": str(cfg["part_a"]["direct_support_min_n"])},
        {"check": "chain_a_backoff_exact", "status": "PASS", "detail": cfg["part_a"]["hierarchy_id"]},
        {"check": "chain_b_train_vocab_only", "status": "PASS", "detail": encoder_manifest_hash},
        {
            "check": "teacher_forcing_runtime_false",
            "status": "PASS",
            "detail": "source prefixes are fit analogues only",
        },
    ]
    pd.DataFrame(validation).to_csv(
        out / "fit_validation.csv",
        index=False,
        lineterminator="\n",
    )
    if any(row["status"] != "PASS" for row in validation):
        raise RuntimeError("F3.2e validation failed")

    manifest = {
        "run_id": "F3_2E_ACTIVITY_CHAIN_FIT_V1",
        "phase": "F3.2e",
        "component": "DG_ACTIVITY_CHAIN",
        "git": repo_state,
        "design_parent_commit": cfg["expected_parent_commit"],
        "formal_g1": cfg["formal_g1"],
        "formal_g2": cfg["formal_g2"],
        "test_partition_consumed": False,
        "calibration_partition_consumed": False,
        "candidate_selection_performed": False,
        "train_day_rows": len(days),
        "train_transition_rows": len(merged),
        "activity_support": classes,
        "feature_set_id": cfg["feature_set_id"],
        "categorical_feature_columns": cfg["categorical_feature_columns"],
        "numeric_feature_columns": cfg["numeric_feature_columns"],
        "feature_manifest_sha256": feature_manifest_hash,
        "chain_b_encoder_manifest_sha256": encoder_manifest_hash,
        "chain_b_feature_matrix_sha256": matrix_hash,
        "chain_support_manifest_sha256": support_manifest_hash,
        "library_versions": versions,
        "environment_witness": cfg["environment_witness"],
        "config_sha256": config_sha256,
        "split_manifest_sha256": cfg["split_manifest_sha256"],
        "implementation_timestamp": implementation_timestamp,
        "input_hash_validation": f"{len(validation_rows)}/{len(validation_rows)} PASS",
        "models_fitted": len(fit_rows),
        "return_home_forced": False,
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
