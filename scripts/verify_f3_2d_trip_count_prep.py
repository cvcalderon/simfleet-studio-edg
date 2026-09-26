from __future__ import annotations

import hashlib
import importlib.metadata
import json
import subprocess
from pathlib import Path

import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "configs/f3/f3_2d_trip_count_fit_v1.yaml"
EXPECTED_PARENT = "b06655ed9c87d19977f8aa8b77ed7cfcbd37d670"
EXPECTED_SPLIT = "5d0d4f2a41bc93b131de96d85192d8ff7002878e28e87515a0f88cedf1cebde8"


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
    for key in ("train_context", "train_trip_count", "vocabulary_manifest", "materialization_manifest"):
        hashes_ok &= (
            sha256_file(materialized / cfg["inputs"][key])
            == cfg["inputs"]["expected_sha256"][key]
        )
    design_ok = all(
        sha256_file(ROOT / witness["path"]) == witness["sha256"]
        for witness in cfg["design_witnesses"].values()
    )
    env_ok = (
        sha256_file(env_root / "environment_manifest.json")
        == cfg["environment_witness"]["environment_manifest_sha256"]
        and sha256_file(env_root / "pip_freeze.txt")
        == cfg["environment_witness"]["pip_freeze_sha256"]
        and sha256_file(env_root / "checksums.sha256")
        == cfg["environment_witness"]["checksums_sha256"]
    )

    count = pd.read_csv(materialized / cfg["inputs"]["train_trip_count"])
    context = pd.read_csv(materialized / cfg["inputs"]["train_context"])
    merged = count.merge(
        context,
        left_on="context_row_id",
        right_on="row_id",
        how="left",
        validate="one_to_one",
        suffixes=("_target", "_context"),
    )
    features = list(cfg["feature_columns"])
    forbidden = [str(token).lower() for token in cfg["forbidden_feature_tokens"]]
    feature_text = "|".join(features).lower()
    grids = list(cfg["part_a"]["grids"]) + [cfg["part_b"]["grid_id"]]
    runner_text = (ROOT / "src/simfleet_edg/repro/f3_2d_fit_trip_count.py").read_text()

    expected_hierarchy = [
        ["age_infr_class", "sex", "primary_activity_status", "household_size_class", "source_weekday"],
        ["age_infr_class", "sex", "primary_activity_status", "household_size_class"],
        ["age_infr_class", "sex", "primary_activity_status"],
        ["age_infr_class", "primary_activity_status"],
        ["primary_activity_status"],
        ["age_infr_class"],
        ["GLOBAL"],
    ]

    checks = {
        "config_present": CONFIG.exists(),
        "head_is_f3_2c_participation_commit": head == EXPECTED_PARENT,
        "parent_exact": cfg["expected_parent_commit"] == EXPECTED_PARENT,
        "formal_g1_open": cfg["formal_g1"] == "OPEN",
        "formal_g2_not_evaluated": cfg["formal_g2"] == "NOT_EVALUATED",
        "test_sealed": cfg["test_partition"] == "SEALED",
        "calibration_do_not_read": cfg["calibration_policy"] == "DO_NOT_READ_DO_NOT_SCORE_DO_NOT_FIT",
        "selection_none": cfg["selection_policy"] == "NONE_IN_F3_2D",
        "train_inputs_hash_exact": bool(hashes_ok),
        "design_hashes_exact": bool(design_ok),
        "environment_hashes_exact": bool(env_ok),
        "environment_versions_exact": actual_versions == cfg["environment_witness"]["required_versions"],
        "split_manifest_hash_frozen": cfg["split_manifest_sha256"] == EXPECTED_SPLIT,
        "train_rows_1791": len(count) == int(cfg["expected_train_rows"]) == 1791,
        "join_rows_1791": len(merged) == 1791,
        "join_missing_context_zero": int(merged["row_id"].isna().sum()) == 0,
        "k_min_1": int(count["target_trip_count"].min()) == int(cfg["k_min"]) == 1,
        "k_max_train_50": int(count["target_trip_count"].max()) == int(cfg["k_max_train"]) == 50,
        "y_equals_k_minus_1": bool(
            (count["target_excess_count"] == count["target_trip_count"] - 1).all()
        ),
        "feature_set_exact": cfg["feature_set_id"] == "COUNT_FEATURES_V1",
        "feature_columns_6": features
        == [
            "age_infr_class",
            "sex",
            "primary_activity_status",
            "household_size_class",
            "source_weekday",
            "source_season",
        ],
        "forbidden_features_absent": not any(token in feature_text for token in forbidden),
        "count_a_grids_exact": cfg["part_a"]["grids"]
        == {
            "CA1": {"lambda_l2": 0.0},
            "CA2": {"lambda_l2": 0.1},
            "CA3": {"lambda_l2": 1.0},
        },
        "count_b_grid_exact": cfg["part_b"]["grid_id"] == "CB1",
        "all_grid_ids_exact": grids == ["CA1", "CA2", "CA3", "CB1"],
        "count_a_train_mle": cfg["part_a"]["dispersion"] == "TRAIN_MLE",
        "count_a_target_excess": cfg["part_a"]["target"] == "Y_EQUALS_K_MINUS_1",
        "count_a_tail_exact": cfg["part_a"]["tail_policy"]
        == "TRUNCATE_AND_RENORMALIZE_NB2_TO_K_1_THROUGH_K_MAX_TRAIN",
        "count_a_no_posthoc_clip": cfg["part_a"]["posthoc_clip"] is False,
        "count_a_reference_one_hot": cfg["count_a_encoder"]["type"]
        == "deterministic_reference_one_hot",
        "count_a_no_rare_pooling": cfg["count_a_encoder"]["rare_pooling"] == "NONE",
        "count_b_hierarchy_exact": cfg["part_b"]["hierarchy"] == expected_hierarchy,
        "count_b_low_n_30": int(cfg["part_b"]["direct_support_min_n"]) == 30,
        "count_b_raw_support_counts": cfg["part_b"]["support_count_basis"]
        == "RAW_STRICT_TRAIN_ROWS_BEFORE_WEIGHTING",
        "count_b_no_smoothing": cfg["part_b"]["smoothing"] == "NONE",
        "season_not_added_to_backoff": all(
            "source_season" not in level for level in cfg["part_b"]["hierarchy"]
        ),
        "fit_seed_rule_frozen": cfg["master_seed"] == 20260926 and "SHA256" in cfg["fit_seed_rule"],
        "runner_has_no_calibration_path": "CALIBRATION/" not in runner_text
        and "CALIBRATION" not in runner_text,
        "runner_has_no_test_path": '"TEST"' not in runner_text and "/TEST" not in runner_text,
        "output_absent": not (ROOT / cfg["output_policy"]["official_output"]).exists(),
        "no_cal_metrics_output": cfg["output_policy"]["cal_metrics_emitted"] is False,
        "no_selection_output": cfg["output_policy"]["selection_decision_emitted"] is False,
        "expected_models_5": int(cfg["output_policy"]["expected_models"]) == 5,
    }
    status = "PASS" if all(checks.values()) else "FAIL"
    print(
        json.dumps(
            {
                "status": status,
                "checks": checks,
                "counts": {
                    "features": len(features),
                    "fit_grids": len(grids),
                    "expected_models": int(cfg["output_policy"]["expected_models"]),
                    "train_rows": len(count),
                    "k_max_train": int(count["target_trip_count"].max()),
                },
                "runtime_versions": actual_versions,
            },
            indent=2,
            sort_keys=True,
        )
    )
    if status != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
