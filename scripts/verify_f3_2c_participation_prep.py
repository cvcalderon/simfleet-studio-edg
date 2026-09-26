from __future__ import annotations

import hashlib
import importlib.metadata
import json
import subprocess
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "configs/f3/f3_2c_participation_fit_v1.yaml"
EXPECTED_PARENT = "f6d93061297bf46f1203d4e5f5914a62c95141ec"


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def main() -> None:
    cfg = yaml.safe_load(CONFIG.read_text())
    materialized = ROOT / cfg["inputs"]["materialized_root"]
    env_root = ROOT / cfg["environment_witness"]["root"]
    head = git("rev-parse", "HEAD")

    actual_versions = {
        name: importlib.metadata.version(name)
        for name in ["numpy", "pandas", "scipy", "scikit-learn", "statsmodels", "lightgbm"]
    }
    hashes_ok = True
    for key in ("train_context", "train_participation", "vocabulary_manifest", "materialization_manifest"):
        hashes_ok &= sha256_file(materialized / cfg["inputs"][key]) == cfg["inputs"]["expected_sha256"][key]
    design_ok = all(sha256_file(ROOT / v["path"]) == v["sha256"] for v in cfg["design_witnesses"].values())
    env_ok = (
        sha256_file(env_root / "environment_manifest.json") == cfg["environment_witness"]["environment_manifest_sha256"]
        and sha256_file(env_root / "pip_freeze.txt") == cfg["environment_witness"]["pip_freeze_sha256"]
        and sha256_file(env_root / "checksums.sha256") == cfg["environment_witness"]["checksums_sha256"]
    )
    features = list(cfg["feature_columns"])
    forbidden = [str(x).lower() for x in cfg["forbidden_feature_tokens"]]
    feature_text = "|".join(features).lower()
    grids = list(cfg["part_a"]["grids"]) + list(cfg["part_b"]["grids"])
    expected_grids = ["PA1", "PA2", "PA3", "PB1", "PB2", "PB3", "PB4"]
    runner_text = (ROOT / "src/simfleet_edg/repro/f3_2c_fit_participation.py").read_text()

    checks = {
        "config_present": CONFIG.exists(),
        "head_is_env_declaration_commit": head == EXPECTED_PARENT,
        "parent_exact": cfg["expected_parent_commit"] == EXPECTED_PARENT,
        "formal_g1_open": cfg["formal_g1"] == "OPEN",
        "formal_g2_not_evaluated": cfg["formal_g2"] == "NOT_EVALUATED",
        "test_sealed": cfg["test_partition"] == "SEALED",
        "calibration_do_not_read": cfg["calibration_policy"] == "DO_NOT_READ_DO_NOT_SCORE_DO_NOT_FIT",
        "selection_none": cfg["selection_policy"] == "NONE_IN_F3_2C",
        "train_inputs_hash_exact": bool(hashes_ok),
        "design_hashes_exact": bool(design_ok),
        "environment_hashes_exact": bool(env_ok),
        "environment_versions_exact": actual_versions == cfg["environment_witness"]["required_versions"],
        "train_rows_2154": int(cfg["expected_train_rows"]) == 2154,
        "split_manifest_hash_frozen": cfg["split_manifest_sha256"] == "5d0d4f2a41bc93b131de96d85192d8ff7002878e28e87515a0f88cedf1cebde8",
        "feature_set_exact": cfg["feature_set_id"] == "PART_FEATURES_V1",
        "feature_columns_15": len(features) == 15,
        "forbidden_features_absent": not any(token in feature_text for token in forbidden),
        "part_a_grids_exact": list(cfg["part_a"]["grids"]) == ["PA1", "PA2", "PA3"],
        "part_b_grids_exact": list(cfg["part_b"]["grids"]) == ["PB1", "PB2", "PB3", "PB4"],
        "all_grid_ids_exact": grids == expected_grids,
        "part_a_lambdas_exact": [cfg["part_a"]["grids"][x]["lambda_l2"] for x in ["PA1", "PA2", "PA3"]] == [0.1, 1.0, 10.0],
        "part_b_grid_exact": cfg["part_b"]["grids"] == {
            "PB1": {"max_depth": 2, "num_leaves": 4, "min_data_in_leaf": 30, "lambda_l2": 1.0},
            "PB2": {"max_depth": 3, "num_leaves": 8, "min_data_in_leaf": 30, "lambda_l2": 1.0},
            "PB3": {"max_depth": 3, "num_leaves": 8, "min_data_in_leaf": 60, "lambda_l2": 1.0},
            "PB4": {"max_depth": 3, "num_leaves": 8, "min_data_in_leaf": 30, "lambda_l2": 10.0},
        },
        "fit_seed_rule_frozen": cfg["master_seed"] == 20260926 and "SHA256" in cfg["fit_seed_rule"],
        "runner_has_no_calibration_path": "CALIBRATION" not in runner_text,
        "runner_has_no_test_path": '"TEST"' not in runner_text and "'/TEST'" not in runner_text,
        "output_absent": not (ROOT / cfg["output_policy"]["official_output"]).exists(),
        "no_cal_metrics_output": cfg["output_policy"]["cal_metrics_emitted"] is False,
        "no_selection_output": cfg["output_policy"]["selection_decision_emitted"] is False,
    }
    status = "PASS" if all(checks.values()) else "FAIL"
    print(json.dumps({"status": status, "checks": checks, "counts": {"features": len(features), "fit_grids": len(grids), "expected_models": 8}, "runtime_versions": actual_versions}, indent=2, sort_keys=True))
    if status != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
