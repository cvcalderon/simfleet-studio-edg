from __future__ import annotations

import hashlib
import importlib.metadata
import json
import subprocess
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import yaml

EXPECTED_PARENT = "8aa9af765ed9aa2d69fe797c1530c88ae55ed5f4"
EXPECTED_OVERLAY = {
    "configs/f3/f3_2f_time_schedule_fit_v1.yaml",
    "docs/F3_2f_TIME_SCHEDULE_EXECUTION_INSTRUCTIONS_v1.md",
    "docs/F3_2f_TIME_SCHEDULE_IMPLEMENTATION_NOTE_v1.md",
    "docs/F3_2f_TIME_SCHEDULE_OBJECTIVE_FREEZE_v1.md",
    "docs/F3_2f_TIME_SCHEDULE_OVERLAY_CHECKSUMS_v1.sha256",
    "docs/F3_2f_TIME_SCHEDULE_OVERLAY_FILELIST_v1.txt",
    "docs/MAIN_UPDATE_F3_2f_TIME_SCHEDULE_PREP_v1.md",
    "notebooks/12_f3_2f_time_schedule_fit.ipynb",
    "scripts/verify_f3_2f_time_schedule_prep.py",
    "src/simfleet_edg/demand/time_schedule.py",
    "src/simfleet_edg/repro/f3_2f_fit_time_schedule.py",
    "tests/test_f3_2f_time_schedule.py",
}


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git(root: Path, *args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=root, text=True).strip()


def config_has_forbidden_partition_paths(obj: Any) -> bool:
    if isinstance(obj, dict):
        for key, value in obj.items():
            low = str(key).lower()
            if "calibration" in low and low not in {"calibration_policy"}:
                if isinstance(value, str) and ("/" in value or value.lower().endswith(".csv")):
                    return True
            if low.startswith("test_") and low != "test_partition":
                if isinstance(value, str) and ("/" in value or value.lower().endswith(".csv")):
                    return True
            if config_has_forbidden_partition_paths(value):
                return True
    elif isinstance(obj, list):
        return any(config_has_forbidden_partition_paths(value) for value in obj)
    return False


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    cfg_path = root / "configs/f3/f3_2f_time_schedule_fit_v1.yaml"
    cfg = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))
    checks: dict[str, bool] = {}

    checks["branch_main"] = git(root, "branch", "--show-current") == "main"
    checks["head_exact_parent"] = git(root, "rev-parse", "HEAD") == EXPECTED_PARENT
    ahead, behind = git(root, "rev-list", "--left-right", "--count", "HEAD...origin/main").split()
    checks["ahead_zero"] = int(ahead) == 0
    checks["behind_zero"] = int(behind) == 0
    checks["upstream_origin_main"] = git(root, "rev-parse", "--abbrev-ref", "@{upstream}") == "origin/main"
    checks["no_tracked_worktree_changes"] = subprocess.run(["git", "diff", "--quiet"], cwd=root).returncode == 0
    checks["no_staged_changes"] = subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=root).returncode == 0

    status_lines = [line for line in git(root, "status", "--porcelain").splitlines() if line]
    untracked = {line[3:] for line in status_lines if line.startswith("?? ")}
    checks["overlay_scope_exact"] = untracked == EXPECTED_OVERLAY and len(status_lines) == len(EXPECTED_OVERLAY)

    checks["formal_g1_open"] = cfg["formal_g1"] == "OPEN"
    checks["formal_g2_not_evaluated"] = cfg["formal_g2"] == "NOT_EVALUATED"
    checks["test_sealed"] = cfg["test_partition"] == "SEALED"
    checks["calibration_do_not_read"] = cfg["calibration_policy"] == "DO_NOT_READ_DO_NOT_SCORE_DO_NOT_FIT"
    checks["selection_none"] = cfg["selection_policy"] == "NONE_IN_F3_2F"
    checks["runner_has_no_cal_test_path"] = not config_has_forbidden_partition_paths(cfg)

    materialized = root / cfg["inputs"]["materialized_root"]
    input_specs = {
        key: materialized / cfg["inputs"][key]
        for key in ("train_context", "train_time_trips", "vocabulary_manifest", "materialization_manifest")
    }
    checks["train_inputs_hash_exact"] = all(
        sha256_file(path) == cfg["inputs"]["expected_sha256"][key]
        for key, path in input_specs.items()
    )
    checks["design_hashes_exact"] = all(
        sha256_file(root / spec["path"]) == spec["sha256"] for spec in cfg["design_witnesses"].values()
    )
    env_root = root / cfg["environment_witness"]["root"]
    env_pairs = {
        "environment_manifest.json": cfg["environment_witness"]["environment_manifest_sha256"],
        "pip_freeze.txt": cfg["environment_witness"]["pip_freeze_sha256"],
        "checksums.sha256": cfg["environment_witness"]["checksums_sha256"],
    }
    checks["environment_hashes_exact"] = all(sha256_file(env_root / name) == expected for name, expected in env_pairs.items())
    versions = {
        name: importlib.metadata.version(name)
        for name in ["numpy", "pandas", "scipy", "scikit-learn", "statsmodels", "lightgbm"]
    }
    required = {name: str(value) for name, value in cfg["environment_witness"]["required_versions"].items()}
    checks["environment_versions_exact"] = versions == required

    context = pd.read_csv(input_specs["train_context"])
    time = pd.read_csv(input_specs["train_time_trips"])
    merged = time.merge(context, left_on="context_row_id", right_on="row_id", how="left", validate="many_to_one")
    checks["context_rows_2200"] = len(context) == 2200
    checks["time_rows_6103"] = len(time) == 6103
    checks["join_rows_6103"] = len(merged) == 6103
    checks["join_missing_context_zero"] = int(merged["row_id"].isna().sum()) == 0
    checks["unresolved_transition_context_329"] = int((time["transition_context_status"] == "UNRESOLVED").sum()) == 329
    checks["missing_k_context_78"] = int(time["source_trip_count_analogue"].isna().sum()) == 78
    checks["missing_time_prefix_1798"] = int(time["previous_arrival_absolute_minute"].isna().sum()) == 1798

    dep = time["target_departure_clock_minute"].astype(float).to_numpy()
    arr = time["target_arrival_clock_minute"].astype(float).to_numpy()
    off = time["target_arrival_day_offset"].astype(int).to_numpy()
    dur = time["target_duration_from_clock_min"].astype(float).to_numpy()
    checks["source_departure_clock_valid"] = bool(np.all((dep >= 0) & (dep < 1440)))
    checks["source_arrival_clock_valid"] = bool(np.all((arr >= 0) & (arr < 1440)))
    checks["source_arrival_offset_0_or_1"] = set(np.unique(off)).issubset({0, 1})
    checks["source_duration_positive"] = bool(np.all(dur >= 1))
    checks["source_arrival_identity_exact"] = bool(np.allclose(arr + 1440 * off - dep, dur, rtol=0.0, atol=1e-12))
    checks["source_offset_one_rows_26"] = int((off == 1).sum()) == 26

    expected_categorical = [
        "age_infr_class", "sex", "primary_activity_status", "household_size_class",
        "source_weekday", "source_season", "origin_activity_analogue",
        "destination_activity_analogue", "trip_position_class",
    ]
    expected_numeric = [
        "source_trip_count_analogue", "previous_departure_clock_minute", "previous_arrival_absolute_minute"
    ]
    checks["feature_set_exact"] = cfg["feature_set_id"] == "TIME_FEATURES_V1"
    checks["categorical_features_exact"] = cfg["categorical_feature_columns"] == expected_categorical
    checks["numeric_features_exact"] = cfg["numeric_feature_columns"] == expected_numeric
    actual_features = set(expected_categorical + expected_numeric)
    forbidden = {str(value).lower() for value in cfg["forbidden_feature_tokens"]}
    checks["forbidden_features_absent"] = not any(feature.lower() in forbidden for feature in actual_features)

    expected_hierarchy = [
        ["origin_activity_analogue", "destination_activity_analogue", "trip_position_class", "primary_activity_status", "source_weekday"],
        ["origin_activity_analogue", "destination_activity_analogue", "trip_position_class", "primary_activity_status"],
        ["origin_activity_analogue", "destination_activity_analogue", "trip_position_class"],
        ["destination_activity_analogue", "trip_position_class"],
        ["trip_position_class"],
        ["GLOBAL"],
    ]
    checks["time_a_hierarchy_exact"] = cfg["part_a"]["hierarchy"] == expected_hierarchy
    checks["time_a_low_n_30"] = int(cfg["part_a"]["direct_support_min_n"]) == 30
    checks["time_a_raw_support_counts"] = cfg["part_a"]["support_count_basis"] == "RAW_STRICT_TRAIN_ROWS_BEFORE_WEIGHTING"
    checks["time_a_max_reject_100"] = int(cfg["part_a"]["max_rejection_attempts"]) == 100
    checks["time_a_grids_exact"] = cfg["part_a"]["grids"] == {"TA1": {"bandwidth_min": 0}, "TA2": {"bandwidth_min": 15}, "TA3": {"bandwidth_min": 30}}
    clar = cfg["part_a"]["kernel_clarification"]
    checks["kernel_clarification_pre_cal"] = clar["status"] == "FROZEN_PRE_CAL_IMPLEMENTATION_CLARIFICATION"
    checks["kernel_shape_exact"] = clar["shape"] == "DISCRETE_CIRCULAR_UNIFORM_INTEGER_V1"
    checks["time_a_no_silent_repair"] = cfg["part_a"]["silent_clock_repair"] is False

    checks["time_b_quantiles_exact"] = [float(q) for q in cfg["part_b"]["quantiles"]] == [0.05, 0.10, 0.25, 0.50, 0.75, 0.90, 0.95]
    checks["time_b_monotone_rule_exact"] = cfg["part_b"]["monotone_repair"] == "cumulative_max_then_linear_interpolation"
    checks["time_b_grids_exact"] = cfg["part_b"]["grids"] == {
        "TB1": {"max_depth": 2, "num_leaves": 4, "min_data_in_leaf": 30, "lambda_l2": 1.0},
        "TB2": {"max_depth": 3, "num_leaves": 8, "min_data_in_leaf": 30, "lambda_l2": 1.0},
        "TB3": {"max_depth": 3, "num_leaves": 8, "min_data_in_leaf": 60, "lambda_l2": 1.0},
    }
    checks["expected_models_7"] = int(cfg["output_policy"]["expected_models"]) == 7
    checks["output_absent"] = not (root / cfg["output_policy"]["official_output"]).exists()

    failed = [name for name, ok in checks.items() if not ok]
    result = {
        "status": "PASS" if not failed else "FAIL",
        "checks": checks,
        "counts": {
            "context_rows": len(context),
            "time_rows": len(time),
            "unresolved_transition_context_rows": int((time["transition_context_status"] == "UNRESOLVED").sum()),
            "expected_models": int(cfg["output_policy"]["expected_models"]),
            "fit_grids": len(cfg["part_a"]["grids"]) + len(cfg["part_b"]["grids"]),
            "time_b_quantiles": len(cfg["part_b"]["quantiles"]),
        },
        "runtime_versions": versions,
        "failed": failed,
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
