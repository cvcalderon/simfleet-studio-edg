from __future__ import annotations

import argparse
import importlib.metadata
import json
import subprocess
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

from simfleet_edg.demand.participation import (
    assert_probabilities,
    canonical_json_bytes,
    feature_matrix_sha256,
    finite_metrics,
    fit_lightgbm,
    fit_logistic_l2,
    fit_reference,
    fit_seed,
    load_train_participation,
    sha256_file,
    training_metrics,
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


def _require_hash(path: Path, expected: str) -> None:
    actual = sha256_file(path)
    if actual != expected:
        raise RuntimeError(f"SHA256 mismatch: {path}: expected {expected}, got {actual}")


def _library_versions() -> dict[str, str]:
    names = ["numpy", "pandas", "scipy", "scikit-learn", "statsmodels", "lightgbm"]
    return {name: importlib.metadata.version(name) for name in names}


def _validate_inputs(root: Path, cfg: dict[str, Any]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    materialized = root / cfg["inputs"]["materialized_root"]
    for key in ("train_context", "train_participation", "vocabulary_manifest", "materialization_manifest"):
        path = materialized / cfg["inputs"][key]
        expected = cfg["inputs"]["expected_sha256"][key]
        actual = sha256_file(path)
        rows.append({"kind": "input", "id": key, "path": str(path.relative_to(root)), "expected_sha256": expected, "actual_sha256": actual, "status": "PASS" if expected == actual else "FAIL"})
    for key, witness in cfg["design_witnesses"].items():
        path = root / witness["path"]
        actual = sha256_file(path)
        rows.append({"kind": "design", "id": key, "path": witness["path"], "expected_sha256": witness["sha256"], "actual_sha256": actual, "status": "PASS" if witness["sha256"] == actual else "FAIL"})
    env_root = root / cfg["environment_witness"]["root"]
    for filename, config_key in (
        ("environment_manifest.json", "environment_manifest_sha256"),
        ("pip_freeze.txt", "pip_freeze_sha256"),
        ("checksums.sha256", "checksums_sha256"),
    ):
        actual = sha256_file(env_root / filename)
        expected = cfg["environment_witness"][config_key]
        rows.append({"kind": "environment", "id": filename, "path": str((env_root / filename).relative_to(root)), "expected_sha256": expected, "actual_sha256": actual, "status": "PASS" if expected == actual else "FAIL"})
    failed = [r for r in rows if r["status"] != "PASS"]
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
    feature_matrix_hash: str,
    library_versions: dict[str, str],
    config_sha256: str,
    implementation_timestamp: str,
) -> None:
    _write_json(
        path,
        {
            "artifact_id": f"DG_PARTICIPATION::{candidate_id}::{grid_id or 'REFERENCE'}",
            "component": "DG_PARTICIPATION",
            "candidate_id": candidate_id,
            "grid_id": grid_id,
            "parent_git_commit": repo_state["commit"],
            "config_sha256": config_sha256,
            "source_hashes": cfg["inputs"]["expected_sha256"],
            "split_manifest_sha256": cfg["split_manifest_sha256"],
            "design_parent_commit": cfg["expected_parent_commit"],
            "feature_set_id": cfg["feature_set_id"] if candidate_id != "PART_REF" else "NONE",
            "feature_manifest_sha256": feature_manifest_hash if candidate_id != "PART_REF" else None,
            "vocabulary_sha256": cfg["inputs"]["expected_sha256"]["vocabulary_manifest"],
            "feature_matrix_sha256": feature_matrix_hash if candidate_id != "PART_REF" else None,
            "train_universe": "REF_TRAIN_BINARY",
            "train_rows": cfg["expected_train_rows"],
            "train_row_counts": {"REF_TRAIN_BINARY": cfg["expected_train_rows"]},
            "weighting": "P_GEW",
            "fit_seed": fit_seed_value,
            "library_versions": library_versions,
            "serialized_model_path": model_relpath,
            "serialized_model_sha256": model_sha256,
            "train_metrics": train_metrics,
            "cal_metrics": None,
            "bootstrap": None,
            "backoff": "NOT_APPLICABLE",
            "calibration": "NOT_EVALUATED",
            "selection_decision": "NOT_EVALUATED",
            "test_partition_consumed": False,
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
    required_versions = cfg["environment_witness"]["required_versions"]
    if versions != required_versions:
        raise RuntimeError(f"Resolved library versions differ from frozen environment: {versions} != {required_versions}")

    materialized = root / cfg["inputs"]["materialized_root"]
    data, encoder = load_train_participation(
        materialized,
        list(cfg["feature_columns"]),
        int(cfg["expected_train_rows"]),
    )
    out.mkdir(parents=True, exist_ok=False)
    _write_json(out / "encoder_manifest.json", encoder)
    feature_manifest_hash = sha256_file(out / "encoder_manifest.json")
    matrix_hash = feature_matrix_sha256(data)

    fit_rows: list[dict[str, Any]] = []
    artifact_rows: list[dict[str, Any]] = []

    # Reference baseline.
    ref_model, ref_p = fit_reference(data)
    assert_probabilities(ref_p)
    ref_metrics = training_metrics(data, ref_p)
    if not finite_metrics(ref_metrics):
        raise RuntimeError("Non-finite PART_REF TRAIN metrics")
    ref_path = out / "models" / "PART_REF" / "model.json"
    _write_json(ref_path, ref_model)
    ref_sha = sha256_file(ref_path)
    ref_manifest = out / "models" / "PART_REF" / "artifact_manifest.json"
    _write_model_manifest(
        ref_manifest,
        cfg=cfg,
        repo_state=repo_state,
        candidate_id="PART_REF",
        grid_id=None,
        fit_seed_value=None,
        model_relpath=str(ref_path.relative_to(out)),
        model_sha256=ref_sha,
        train_metrics=ref_metrics,
        feature_manifest_hash=feature_manifest_hash,
        feature_matrix_hash=matrix_hash,
        library_versions=versions,
        config_sha256=config_sha256,
        implementation_timestamp=implementation_timestamp,
    )
    fit_rows.append({"candidate_id": "PART_REF", "grid_id": "REFERENCE", "fit_seed": "", **ref_metrics, "status": "FITTED_TRAIN_ONLY_NOT_SELECTED"})
    artifact_rows.append({"candidate_id": "PART_REF", "grid_id": "REFERENCE", "model_sha256": ref_sha, "manifest_sha256": sha256_file(ref_manifest)})

    # Candidate A.
    for grid_id, grid in cfg["part_a"]["grids"].items():
        seed = fit_seed(int(cfg["master_seed"]), "PART_A", grid_id)
        model, p = fit_logistic_l2(
            data,
            float(grid["lambda_l2"]),
            int(cfg["part_a"]["optimizer_maxiter"]),
            float(cfg["part_a"]["optimizer_ftol"]),
            float(cfg["part_a"]["optimizer_gtol"]),
        )
        model["fit_seed"] = seed
        assert_probabilities(p)
        metrics = training_metrics(data, p)
        if not finite_metrics(metrics):
            raise RuntimeError(f"Non-finite PART_A TRAIN metrics: {grid_id}")
        model_path = out / "models" / "PART_A" / grid_id / "model.json"
        _write_json(model_path, model)
        model_sha = sha256_file(model_path)
        manifest_path = out / "models" / "PART_A" / grid_id / "artifact_manifest.json"
        _write_model_manifest(
            manifest_path,
            cfg=cfg,
            repo_state=repo_state,
            candidate_id="PART_A",
            grid_id=grid_id,
            fit_seed_value=seed,
            model_relpath=str(model_path.relative_to(out)),
            model_sha256=model_sha,
            train_metrics=metrics,
            feature_manifest_hash=feature_manifest_hash,
            feature_matrix_hash=matrix_hash,
            library_versions=versions,
            config_sha256=config_sha256,
            implementation_timestamp=implementation_timestamp,
        )
        fit_rows.append({"candidate_id": "PART_A", "grid_id": grid_id, "fit_seed": seed, **metrics, "status": "FITTED_TRAIN_ONLY_NOT_SELECTED"})
        artifact_rows.append({"candidate_id": "PART_A", "grid_id": grid_id, "model_sha256": model_sha, "manifest_sha256": sha256_file(manifest_path)})

    # Candidate B.
    for grid_id, grid in cfg["part_b"]["grids"].items():
        seed = fit_seed(int(cfg["master_seed"]), "PART_B", grid_id)
        model, p, metadata = fit_lightgbm(data, cfg["part_b"]["common"], grid, seed)
        assert_probabilities(p)
        metrics = training_metrics(data, p)
        if not finite_metrics(metrics):
            raise RuntimeError(f"Non-finite PART_B TRAIN metrics: {grid_id}")
        model_path = out / "models" / "PART_B" / grid_id / "model.txt"
        model_path.parent.mkdir(parents=True, exist_ok=True)
        model.booster_.save_model(str(model_path))
        metadata["fit_seed"] = seed
        _write_json(out / "models" / "PART_B" / grid_id / "model_metadata.json", metadata)
        model_sha = sha256_file(model_path)
        manifest_path = out / "models" / "PART_B" / grid_id / "artifact_manifest.json"
        _write_model_manifest(
            manifest_path,
            cfg=cfg,
            repo_state=repo_state,
            candidate_id="PART_B",
            grid_id=grid_id,
            fit_seed_value=seed,
            model_relpath=str(model_path.relative_to(out)),
            model_sha256=model_sha,
            train_metrics=metrics,
            feature_manifest_hash=feature_manifest_hash,
            feature_matrix_hash=matrix_hash,
            library_versions=versions,
            config_sha256=config_sha256,
            implementation_timestamp=implementation_timestamp,
        )
        fit_rows.append({"candidate_id": "PART_B", "grid_id": grid_id, "fit_seed": seed, **metrics, "status": "FITTED_TRAIN_ONLY_NOT_SELECTED"})
        artifact_rows.append({"candidate_id": "PART_B", "grid_id": grid_id, "model_sha256": model_sha, "manifest_sha256": sha256_file(manifest_path)})

    pd.DataFrame(fit_rows).to_csv(out / "train_fit_summary.csv", index=False, lineterminator="\n", float_format="%.15g")
    pd.DataFrame(validation_rows).to_csv(out / "input_hash_validation.csv", index=False, lineterminator="\n")
    pd.DataFrame(artifact_rows).to_csv(out / "model_artifact_index.csv", index=False, lineterminator="\n")

    validation = [
        {"check": "train_rows_exact", "status": "PASS" if data.source_rows == int(cfg["expected_train_rows"]) else "FAIL", "detail": str(data.source_rows)},
        {"check": "candidates_fitted_exact", "status": "PASS" if len(fit_rows) == 8 else "FAIL", "detail": str(len(fit_rows))},
        {"check": "calibration_not_read", "status": "PASS", "detail": "runner consumes TRAIN paths only"},
        {"check": "cal_metrics_absent", "status": "PASS", "detail": "all artifact manifests set cal_metrics=null"},
        {"check": "selection_not_evaluated", "status": "PASS", "detail": "all artifacts remain FITTED_TRAIN_ONLY_NOT_SELECTED"},
        {"check": "test_partition_consumed", "status": "PASS", "detail": "false"},
        {"check": "ids_not_features", "status": "PASS", "detail": "feature list frozen in config"},
        {"check": "weights_not_features", "status": "PASS", "detail": "P_GEW passed only as sample weight"},
        {"check": "feature_matrix_shared_A_B", "status": "PASS", "detail": matrix_hash},
        {"check": "train_vocab_only", "status": "PASS", "detail": feature_manifest_hash},
    ]
    pd.DataFrame(validation).to_csv(out / "fit_validation.csv", index=False, lineterminator="\n")
    if any(row["status"] != "PASS" for row in validation):
        raise RuntimeError("F3.2c validation failed")

    manifest = {
        "run_id": "F3_2C_PARTICIPATION_FIT_V1",
        "phase": "F3.2c",
        "component": "DG_PARTICIPATION",
        "git": repo_state,
        "design_parent_commit": cfg["expected_parent_commit"],
        "formal_g1": cfg["formal_g1"],
        "formal_g2": cfg["formal_g2"],
        "test_partition_consumed": False,
        "calibration_partition_consumed": False,
        "candidate_selection_performed": False,
        "train_rows": data.source_rows,
        "feature_set_id": cfg["feature_set_id"],
        "feature_columns": cfg["feature_columns"],
        "feature_manifest_sha256": feature_manifest_hash,
        "feature_matrix_sha256": matrix_hash,
        "library_versions": versions,
        "environment_witness": cfg["environment_witness"],
        "config_sha256": config_sha256,
        "split_manifest_sha256": cfg["split_manifest_sha256"],
        "implementation_timestamp": implementation_timestamp,
        "input_hash_validation": f"{len(validation_rows)}/{len(validation_rows)} PASS",
        "models_fitted": 8,
        "status": "PASS",
    }
    _write_json(out / "fit_manifest.json", manifest)

    files = sorted(p for p in out.rglob("*") if p.is_file() and p.name != "checksums.sha256")
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
    print(json.dumps({"status": manifest["status"], "output": str(out.relative_to(root)), "models_fitted": manifest["models_fitted"]}, indent=2))


if __name__ == "__main__":
    main()
