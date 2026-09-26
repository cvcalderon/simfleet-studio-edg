from __future__ import annotations

import csv
import json
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "configs/design/f3_1c_fit_cal_protocol_v1.yaml"


def load_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def main() -> None:
    c = yaml.safe_load(CONTRACT.read_text(encoding="utf-8"))
    features = load_csv(ROOT / "docs/F3_1c_FEATURE_SUBSETS_v1.csv")
    objectives = load_csv(ROOT / "docs/F3_1c_OBJECTIVE_METRIC_REGISTRY_v1.csv")
    hp = load_csv(ROOT / "docs/F3_1c_HYPERPARAMETER_GRID_v1.csv")
    thresholds = load_csv(ROOT / "docs/F3_1c_ACCEPTANCE_THRESHOLDS_v1.csv")
    decisions = load_csv(ROOT / "docs/F3_1c_DECISION_REGISTER_v1.csv")

    checks: dict[str, bool] = {}
    checks["contract_present"] = CONTRACT.exists()
    checks["parent_f3_1b_exact"] = c["required_parent_commit"] == "ce99ff2f175fcc2df34cca3607754b4de9c4605d"
    checks["test_sealed"] = c["test_partition"] == "SEALED"
    checks["formal_g2_not_evaluated"] = c["formal_g2"] == "NOT_EVALUATED"
    checks["lexicographic_no_composite"] = c["selection_rule"]["type"] == "LEXICOGRAPHIC_NO_COMPOSITE_SCORE"
    checks["same_semantic_features_A_B"] = c["feature_policy"]["candidate_A_and_B_same_semantic_feature_subset"] is True
    checks["weights_not_features"] = c["feature_policy"]["weights_are_fit_weights_not_features"] is True
    checks["ids_not_features"] = c["feature_policy"]["technical_ids_are_keys_not_features"] is True
    checks["silent_rare_pooling_forbidden"] = c["feature_policy"]["silent_rare_category_pooling"] is False
    checks["five_components"] = set(c["components"]) == {"DG_PARTICIPATION", "DG_TRIP_COUNT", "DG_ACTIVITY_CHAIN", "DG_TIME_SCHEDULE", "DG_DISTANCE_PRIOR"}
    checks["count_positive_truncated_nb"] = "truncated and renormalized" in c["components"]["DG_TRIP_COUNT"]["tail_policy"]
    checks["teacher_forcing_cal_only"] = c["components"]["DG_ACTIVITY_CHAIN"]["teacher_forcing_for_component_cal_only"] is True and c["components"]["DG_ACTIVITY_CHAIN"]["runtime_teacher_forcing"] is False
    checks["time_planned_not_executed"] = "not executed route travel time" in c["components"]["DG_TIME_SCHEDULE"]["semantic_guardrail"]
    checks["distance_raw_primary"] = c["components"]["DG_DISTANCE_PRIOR"]["train_universe"] == "REF_TRAIN_DISTANCE_RAW"
    checks["low_n_30"] = c["low_support"]["threshold_raw_source_rows"] == 30
    checks["low_n_report_only"] = c["low_support"]["low_n_subgroups"] == "REPORT_ONLY_NEVER_SILENTLY_POOLED"
    checks["four_backoff_hierarchies"] = len(c["backoff_hierarchies"]) == 4
    checks["master_seed_frozen"] = c["seed_contract"]["master_seed"] == 20260926
    checks["common_random_numbers"] = c["seed_contract"]["common_random_numbers"] is True
    checks["cal_replicates_32"] = c["calibration_protocol"]["stochastic_replicates_per_cal_person"] == 32
    checks["bootstrap_household_1000"] = c["calibration_protocol"]["bootstrap"]["unit"] == "HOUSEHOLD" and c["calibration_protocol"]["bootstrap"]["replicates"] == 1000
    checks["bootstrap_95"] = c["calibration_protocol"]["bootstrap"]["confidence_level"] == 0.95
    checks["promotion_margins_five"] = len([k for k in c["promotion_margins"] if k != "rule" and k != "interpretation"]) == 5
    checks["zero_tolerance_hard"] = c["guardrail_tolerances"]["structural_invariant_violations"] == 0 and c["guardrail_tolerances"]["nofuture_violations"] == 0 and c["guardrail_tolerances"]["temporal_invariant_violations"] == 0
    checks["joint_gate_before_test"] = c["joint_pipeline_cal_gate_before_test"]["test_opening_requires_frozen_artifact_manifest"] is True
    checks["artifact_manifest_fields"] = len(c["artifact_manifest_required_fields"]) >= 15
    checks["no_cal_redesign"] = "changing_feature_subset_after_inspecting_CAL" in c["forbidden_during_cal"] and "changing_promotion_margin_after_inspecting_CAL" in c["forbidden_during_cal"]
    checks["feature_rows_15"] = len(features) == 15
    checks["objective_rows_15"] = len(objectives) == 15
    checks["hyperparameter_grid_nonempty"] = len(hp) >= 20
    checks["threshold_registry_nonempty"] = len(thresholds) >= 10
    checks["decisions_17"] = len(decisions) == 17

    status = "PASS" if all(checks.values()) else "FAIL"
    print(json.dumps({
        "status": status,
        "checks": checks,
        "counts": {
            "feature_rows": len(features),
            "objective_rows": len(objectives),
            "hyperparameter_rows": len(hp),
            "threshold_rows": len(thresholds),
            "decisions": len(decisions),
        },
    }, indent=2))
    raise SystemExit(0 if status == "PASS" else 1)


if __name__ == "__main__":
    main()
