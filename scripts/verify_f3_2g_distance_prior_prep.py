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

EXPECTED_PARENT = "799d5c6085c7c29ba7e83e02d37b37aac22ee296"
EXPECTED_OVERLAY = {
    "configs/f3/f3_2g_distance_prior_fit_v1.yaml",
    "docs/F3_2g_DISTANCE_PRIOR_EXECUTION_INSTRUCTIONS_v1.md",
    "docs/F3_2g_DISTANCE_PRIOR_IMPLEMENTATION_CLARIFICATIONS_v1.md",
    "docs/F3_2g_DISTANCE_PRIOR_IMPLEMENTATION_NOTE_v1.md",
    "docs/F3_2g_DISTANCE_PRIOR_OBJECTIVE_FREEZE_v1.md",
    "docs/F3_2g_DISTANCE_PRIOR_SOURCE_AUDIT_ERRATA_v1.md",
    "docs/F3_2g_DISTANCE_PRIOR_OVERLAY_CHECKSUMS_v1.sha256",
    "docs/F3_2g_DISTANCE_PRIOR_OVERLAY_FILELIST_v1.txt",
    "docs/MAIN_UPDATE_F3_2g_DISTANCE_PRIOR_PREP_v1.md",
    "notebooks/13_f3_2g_distance_prior_fit.ipynb",
    "scripts/verify_f3_2g_distance_prior_prep.py",
    "src/simfleet_edg/demand/distance_prior.py",
    "src/simfleet_edg/repro/f3_2g_fit_distance_prior.py",
    "tests/test_f3_2g_distance_prior.py",
}


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git(root: Path, *args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=root, text=True).strip()


def config_has_forbidden_partition_paths(obj: Any) -> bool:
    if isinstance(obj, dict):
        for key, value in obj.items():
            low = str(key).lower()
            if "calibration" in low and low not in {"calibration_policy", "calibration_partition_consumed"}:
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
    cfg_path = root / "configs/f3/f3_2g_distance_prior_fit_v1.yaml"
    cfg = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))
    checks: dict[str, bool] = {}

    checks["branch_main"] = git(root, "branch", "--show-current") == "main"
    checks["head_exact_parent"] = git(root, "rev-parse", "HEAD") == EXPECTED_PARENT
    upstream = git(root, "rev-parse", "--abbrev-ref", "@{upstream}")
    checks["upstream_origin_main"] = upstream == "origin/main"
    ahead, behind = git(root, "rev-list", "--left-right", "--count", "HEAD...@{upstream}").split()
    checks["ahead_zero"] = int(ahead) == 0
    checks["behind_zero"] = int(behind) == 0
    checks["no_staged_changes"] = git(root, "diff", "--cached", "--name-only") == ""
    checks["no_tracked_worktree_changes"] = git(root, "diff", "--name-only") == ""

    status_lines = [line for line in git(root, "status", "--porcelain").splitlines() if line]
    untracked = {line[3:] for line in status_lines if line.startswith("?? ")}
    checks["overlay_scope_exact"] = untracked == EXPECTED_OVERLAY

    checksums = root / "docs/F3_2g_DISTANCE_PRIOR_OVERLAY_CHECKSUMS_v1.sha256"
    checksum_ok = True
    for line in checksums.read_text(encoding="utf-8").splitlines():
        expected, rel = line.split(maxsplit=1)
        checksum_ok &= sha256_file(root / rel) == expected
    checks["overlay_checksums_exact"] = checksum_ok

    checks["formal_g1_open"] = cfg["formal_g1"] == "OPEN"
    checks["formal_g2_not_evaluated"] = cfg["formal_g2"] == "NOT_EVALUATED"
    checks["test_sealed"] = cfg["test_partition"] == "SEALED"
    checks["calibration_do_not_read"] = cfg["calibration_policy"] == "DO_NOT_READ_DO_NOT_SCORE_DO_NOT_FIT"
    checks["selection_none"] = cfg["selection_policy"] == "NONE_IN_F3_2G"
    checks["runner_has_no_cal_test_path"] = not config_has_forbidden_partition_paths(cfg)

    materialized = root / cfg["inputs"]["materialized_root"]
    input_paths = {
        "train_context": materialized / cfg["inputs"]["train_context"],
        "train_distance_raw": materialized / cfg["inputs"]["train_distance_raw"],
        "train_distance_expanded_sensitivity": materialized / cfg["inputs"]["train_distance_expanded_sensitivity"],
        "vocabulary_manifest": materialized / cfg["inputs"]["vocabulary_manifest"],
        "materialization_manifest": materialized / cfg["inputs"]["materialization_manifest"],
    }
    checks["train_inputs_hash_exact"] = all(
        sha256_file(path) == cfg["inputs"]["expected_sha256"][key]
        for key, path in input_paths.items()
    )
    checks["design_hashes_exact"] = all(
        sha256_file(root / spec["path"]) == spec["sha256"]
        for spec in cfg["design_witnesses"].values()
    )
    env_root = root / cfg["environment_witness"]["root"]
    env_hashes = {
        "environment_manifest.json": cfg["environment_witness"]["environment_manifest_sha256"],
        "pip_freeze.txt": cfg["environment_witness"]["pip_freeze_sha256"],
        "checksums.sha256": cfg["environment_witness"]["checksums_sha256"],
    }
    checks["environment_hashes_exact"] = all(
        sha256_file(env_root / name) == expected for name, expected in env_hashes.items()
    )
    versions = {
        name: importlib.metadata.version(name)
        for name in ["numpy", "pandas", "scipy", "scikit-learn", "statsmodels", "lightgbm"]
    }
    expected_versions = {key: str(value) for key, value in cfg["environment_witness"]["required_versions"].items()}
    checks["environment_versions_exact"] = versions == expected_versions

    context = pd.read_csv(input_paths["train_context"])
    raw = pd.read_csv(input_paths["train_distance_raw"])
    sensitivity = pd.read_csv(input_paths["train_distance_expanded_sensitivity"])
    joined = raw.merge(context, left_on="context_row_id", right_on="row_id", how="left", validate="many_to_one")

    checks["context_rows_2200"] = len(context) == 2200
    checks["distance_raw_rows_5617"] = len(raw) == 5617
    checks["distance_sensitivity_rows_6145"] = len(sensitivity) == 6145
    checks["join_rows_5617"] = len(joined) == 5617
    checks["join_missing_context_zero"] = not joined["row_id"].isna().any()
    checks["missing_trip_count_80"] = int(raw["source_trip_count_analogue"].isna().sum()) == 80
    checks["missing_time_context_32"] = int((raw["time_context_status"] == "MISSING_SOURCE_CONTEXT").sum()) == 32
    checks["unresolved_transition_context_217"] = int((raw["transition_context_status"] == "UNRESOLVED").sum()) == 217
    checks["raw_target_positive_finite"] = bool(np.isfinite(raw["target_distance_prior_km"]).all() and (raw["target_distance_prior_km"] > 0).all())
    checks["raw_provenance_only"] = set(raw["distance_provenance"].astype(str).unique()) == {"RAW_WEGKM"}
    checks["sensitivity_has_imputed_rows"] = int((sensitivity["distance_provenance"] == "SOURCE_IMPUTED_WEGKM").sum()) == 528

    expected_cat = [
        "age_infr_class",
        "sex",
        "primary_activity_status",
        "household_size_class",
        "source_weekday",
        "source_season",
        "origin_activity_analogue",
        "destination_activity_analogue",
        "departure_period_analogue",
    ]
    expected_num = [
        "source_trip_count_analogue",
        "departure_clock_minute_analogue",
        "arrival_clock_minute_analogue",
        "duration_from_clock_min_analogue",
    ]
    checks["categorical_features_exact"] = cfg["categorical_feature_columns"] == expected_cat
    checks["numeric_features_exact"] = cfg["numeric_feature_columns"] == expected_num
    actual_features = expected_cat + expected_num
    forbidden = {str(value).lower() for value in cfg["forbidden_feature_tokens"]}
    checks["forbidden_features_absent"] = not any(feature.lower() in forbidden for feature in actual_features)
    checks["km_routing_forbidden"] = "km_routing" in forbidden
    checks["quality_flags_not_features"] = "time_context_status" not in actual_features and "transition_context_status" not in actual_features

    expected_hierarchy = [
        ["origin_activity_analogue", "destination_activity_analogue", "departure_period_analogue", "primary_activity_status", "age_infr_class"],
        ["origin_activity_analogue", "destination_activity_analogue", "departure_period_analogue", "primary_activity_status"],
        ["origin_activity_analogue", "destination_activity_analogue", "departure_period_analogue"],
        ["origin_activity_analogue", "destination_activity_analogue"],
        ["destination_activity_analogue"],
        ["GLOBAL"],
    ]
    checks["distance_a_hierarchy_exact"] = cfg["part_a"]["hierarchy"] == expected_hierarchy
    checks["distance_a_low_n_30"] = int(cfg["part_a"]["direct_support_min_n"]) == 30
    checks["distance_a_raw_support_counts"] = cfg["part_a"]["support_count_basis"] == "RAW_STRICT_TRAIN_ROWS_BEFORE_WEIGHTING"
    checks["distance_a_grid_exact"] = cfg["part_a"]["grids"] == {"DA1": {"inverse_ecdf_interpolation": "LINEAR_WEIGHTED"}}

    clar = cfg["implementation_clarifications"]
    checks["clarifications_pre_cal"] = clar["status"] == "FROZEN_PRE_CAL_IMPLEMENTATION_CLARIFICATIONS"
    checks["encoder_clarification_exact"] = clar["encoder"]["id"] == "DIST_FEATURES_V1_ENCODER_V1"
    checks["inverse_ecdf_clarification_exact"] = clar["inverse_ecdf"]["id"] == "LINEAR_WEIGHTED_CUMULATIVE_MASS_KNOTS_V1"
    checks["dist_b_common_clarification_exact"] = clar["dist_b_training_common"] == {
        "id": "DIST_B_COMMON_TRAINING_V1",
        "reason": "F3.1c DIST_B rows froze quantiles/depth/leaves/min_leaf/L2 but did not state learning rate or estimator count",
        "learning_rate": 0.05,
        "n_estimators": 200,
    }
    checks["dist_b_reconstruction_clarification_exact"] = clar["dist_b_reconstruction"]["id"] == "DIST_B_QUANTILE_RECONSTRUCTION_V1"

    checks["distance_b_quantiles_exact"] = [float(value) for value in cfg["part_b"]["quantiles"]] == [0.05, 0.10, 0.25, 0.50, 0.75, 0.90, 0.95]
    checks["distance_b_common_exact"] = cfg["part_b"]["common"] == {"learning_rate": 0.05, "n_estimators": 200}
    checks["distance_b_grids_exact"] = cfg["part_b"]["grids"] == {
        "DB1": {"max_depth": 2, "num_leaves": 4, "min_data_in_leaf": 30, "lambda_l2": 1.0},
        "DB2": {"max_depth": 3, "num_leaves": 8, "min_data_in_leaf": 30, "lambda_l2": 1.0},
        "DB3": {"max_depth": 3, "num_leaves": 8, "min_data_in_leaf": 60, "lambda_l2": 1.0},
    }
    checks["primary_target_raw_wegkm"] = cfg["primary_target"]["evidence"] == "RAW_WEGKM"
    checks["sensitivity_report_only"] = cfg["sensitivity_target"]["role"] == "REPORT_ONLY_NOT_PRIMARY_FIT" and cfg["sensitivity_target"]["consumed_for_primary_fit"] is False
    checks["expected_models_5"] = int(cfg["output_policy"]["expected_models"]) == 5
    checks["output_absent"] = not (root / cfg["output_policy"]["official_output"]).exists()

    failed = [name for name, ok in checks.items() if not ok]
    result = {
        "status": "PASS" if not failed else "FAIL",
        "checks": checks,
        "counts": {
            "context_rows": len(context),
            "distance_raw_rows": len(raw),
            "distance_sensitivity_rows": len(sensitivity),
            "missing_trip_count_rows": int(raw["source_trip_count_analogue"].isna().sum()),
            "missing_time_context_rows": int((raw["time_context_status"] == "MISSING_SOURCE_CONTEXT").sum()),
            "unresolved_transition_context_rows": int((raw["transition_context_status"] == "UNRESOLVED").sum()),
            "source_imputed_sensitivity_rows": int((sensitivity["distance_provenance"] == "SOURCE_IMPUTED_WEGKM").sum()),
            "expected_models": int(cfg["output_policy"]["expected_models"]),
            "fit_grids": len(cfg["part_a"]["grids"]) + len(cfg["part_b"]["grids"]),
            "distance_b_quantiles": len(cfg["part_b"]["quantiles"]),
        },
        "runtime_versions": versions,
        "failed": failed,
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
