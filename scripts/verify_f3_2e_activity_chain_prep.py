from __future__ import annotations

import hashlib
import importlib.metadata
import json
import subprocess
from pathlib import Path

import pandas as pd
import yaml

from simfleet_edg.demand.activity_chain import target_activity_classes, validate_chain_structure

ROOT = Path(__file__).resolve().parents[1]
CFG_PATH = ROOT / "configs/f3/f3_2e_activity_chain_fit_v1.yaml"
EXPECTED_PARENT = "a69389d904c526c1b8c320f4354b42ab9bfa7a18"
EXPECTED_SPLIT = "5d0d4f2a41bc93b131de96d85192d8ff7002878e28e87515a0f88cedf1cebde8"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def main() -> None:
    cfg = yaml.safe_load(CFG_PATH.read_text())
    head = git("rev-parse", "HEAD")
    branch = git("branch", "--show-current")
    upstream = git("rev-parse", "--abbrev-ref", "@{upstream}")
    ahead, behind = [
        int(value)
        for value in git("rev-list", "--left-right", "--count", "HEAD...@{upstream}").split()
    ]

    materialized = ROOT / cfg["inputs"]["materialized_root"]
    input_ok = True
    for key in (
        "train_context",
        "train_chain_days",
        "train_chain_transitions",
        "vocabulary_manifest",
        "materialization_manifest",
    ):
        actual = sha256_file(materialized / cfg["inputs"][key])
        input_ok &= actual == cfg["inputs"]["expected_sha256"][key]

    design_ok = True
    for witness in cfg["design_witnesses"].values():
        design_ok &= sha256_file(ROOT / witness["path"]) == witness["sha256"]

    env_root = ROOT / cfg["environment_witness"]["root"]
    env_ok = all(
        [
            sha256_file(env_root / "environment_manifest.json")
            == cfg["environment_witness"]["environment_manifest_sha256"],
            sha256_file(env_root / "pip_freeze.txt")
            == cfg["environment_witness"]["pip_freeze_sha256"],
            sha256_file(env_root / "checksums.sha256")
            == cfg["environment_witness"]["checksums_sha256"],
        ]
    )

    required_versions = cfg["environment_witness"]["required_versions"]
    actual_versions = {
        name: importlib.metadata.version(name)
        for name in ["numpy", "pandas", "scipy", "scikit-learn", "statsmodels", "lightgbm"]
    }

    context = pd.read_csv(materialized / cfg["inputs"]["train_context"])
    days = pd.read_csv(materialized / cfg["inputs"]["train_chain_days"])
    transitions = pd.read_csv(materialized / cfg["inputs"]["train_chain_transitions"])
    validate_chain_structure(days, transitions)
    merged = transitions.merge(
        context,
        left_on="context_row_id",
        right_on="row_id",
        how="left",
        validate="many_to_one",
    )
    target_classes = target_activity_classes(merged)

    features = cfg["categorical_feature_columns"] + cfg["numeric_feature_columns"]
    feature_text = "|".join(features).lower()
    forbidden = [str(token).lower() for token in cfg["forbidden_feature_tokens"]]
    grids = list(cfg["part_a"]["grids"]) + list(cfg["part_b"]["grids"])

    expected_hierarchy = [
        [
            "prefix_second_last_activity",
            "prefix_last_activity",
            "remaining_trips",
            "primary_activity_status",
            "source_weekday",
        ],
        ["prefix_last_activity", "remaining_trips", "primary_activity_status", "source_weekday"],
        ["prefix_last_activity", "remaining_trips", "primary_activity_status"],
        ["prefix_last_activity", "remaining_trips"],
        ["prefix_last_activity"],
        ["remaining_trips"],
        ["GLOBAL"],
    ]

    runner_text = (
        ROOT / "src/simfleet_edg/repro/f3_2e_fit_activity_chain.py"
    ).read_text()

    checks = {
        "head_exact_parent": head == EXPECTED_PARENT == cfg["expected_parent_commit"],
        "branch_main": branch == "main",
        "upstream_origin_main": upstream == "origin/main",
        "ahead_zero": ahead == 0,
        "behind_zero": behind == 0,
        "formal_g1_open": cfg["formal_g1"] == "OPEN",
        "formal_g2_not_evaluated": cfg["formal_g2"] == "NOT_EVALUATED",
        "test_sealed": cfg["test_partition"] == "SEALED",
        "calibration_do_not_read": cfg["calibration_policy"]
        == "DO_NOT_READ_DO_NOT_SCORE_DO_NOT_FIT",
        "selection_none": cfg["selection_policy"] == "NONE_IN_F3_2E",
        "train_inputs_hash_exact": bool(input_ok),
        "design_hashes_exact": bool(design_ok),
        "environment_hashes_exact": bool(env_ok),
        "environment_versions_exact": actual_versions == required_versions,
        "split_manifest_hash_frozen": cfg["split_manifest_sha256"] == EXPECTED_SPLIT,
        "context_rows_2200": len(context) == int(cfg["expected_context_rows"]) == 2200,
        "chain_days_1422": len(days) == int(cfg["expected_train_day_rows"]) == 1422,
        "chain_transitions_4872": len(transitions)
        == int(cfg["expected_train_transition_rows"])
        == 4872,
        "join_rows_4872": len(merged) == 4872,
        "join_missing_context_zero": int(merged["row_id"].isna().sum()) == 0,
        "sum_k_equals_transitions": int(days["source_trip_count_analogue"].sum()) == 4872,
        "all_first_origins_home_in_materialized_train": set(days["first_origin_activity"])
        == {"HOME"},
        "target_activity_support_9": target_classes
        == [
            "BUSINESS",
            "EDUCATION",
            "ESCORT",
            "HOME",
            "LEISURE",
            "OTHER",
            "PRIVATE_ERRAND",
            "SHOPPING",
            "WORK",
        ],
        "feature_set_exact": cfg["feature_set_id"] == "CHAIN_FEATURES_V1",
        "categorical_features_exact": cfg["categorical_feature_columns"]
        == [
            "age_infr_class",
            "sex",
            "primary_activity_status",
            "household_size_class",
            "source_weekday",
            "prefix_second_last_activity",
            "prefix_last_activity",
        ],
        "numeric_features_exact": cfg["numeric_feature_columns"]
        == ["source_trip_count_analogue", "remaining_trips"],
        "forbidden_features_absent": not any(token in feature_text for token in forbidden),
        "purpose_not_predictor": "canonical_trip_purpose" not in features,
        "season_not_in_core_chain_features": "source_season" not in features,
        "chain_a_grids_exact": cfg["part_a"]["grids"]
        == {"CHA1": {"dirichlet_alpha": 0.1}, "CHA2": {"dirichlet_alpha": 1.0}},
        "chain_b_grids_exact": cfg["part_b"]["grids"]
        == {
            "CHB1": {"lambda_l2": 0.1},
            "CHB2": {"lambda_l2": 1.0},
            "CHB3": {"lambda_l2": 10.0},
        },
        "all_grid_ids_exact": grids == ["CHA1", "CHA2", "CHB1", "CHB2", "CHB3"],
        "chain_a_hierarchy_exact": cfg["part_a"]["hierarchy"] == expected_hierarchy,
        "chain_a_low_n_30": int(cfg["part_a"]["direct_support_min_n"]) == 30,
        "chain_a_raw_support_counts": cfg["part_a"]["support_count_basis"]
        == "RAW_STRICT_TRAIN_ROWS_BEFORE_WEIGHTING",
        "chain_a_weight_w_gew": cfg["part_a"]["probability_weight"] == "W_GEW",
        "chain_a_start_token": cfg["part_a"]["start_token"] == "__START__",
        "return_home_not_forced": cfg["return_home_forced"] is False
        and cfg["part_a"]["return_home_forced"] is False,
        "chain_b_family_exact": cfg["part_b"]["family"]
        == "REGULARIZED_MULTINOMIAL_LOGISTIC_NEXT_ACTIVITY",
        "chain_b_train_encoder": cfg["part_b"]["encoder"]["source"] == "TRAIN_ONLY",
        "chain_b_no_rare_pooling": cfg["part_b"]["encoder"]["rare_pooling"] == "NONE",
        "fit_seed_rule_frozen": cfg["master_seed"] == 20260926 and "SHA256" in cfg["fit_seed_rule"],
        "runner_has_no_calibration_path": "CALIBRATION/" not in runner_text,
        "runner_has_no_test_path": '"TEST"' not in runner_text and "/TEST" not in runner_text,
        "output_absent": not (ROOT / cfg["output_policy"]["official_output"]).exists(),
        "no_cal_metrics_output": cfg["output_policy"]["cal_metrics_emitted"] is False,
        "no_selection_output": cfg["output_policy"]["selection_decision_emitted"] is False,
        "expected_models_6": int(cfg["output_policy"]["expected_models"]) == 6,
    }
    status = "PASS" if all(checks.values()) else "FAIL"
    print(
        json.dumps(
            {
                "status": status,
                "checks": checks,
                "counts": {
                    "context_rows": len(context),
                    "chain_days": len(days),
                    "chain_transitions": len(transitions),
                    "target_classes": len(target_classes),
                    "fit_grids": len(grids),
                    "expected_models": int(cfg["output_policy"]["expected_models"]),
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
