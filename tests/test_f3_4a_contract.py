from pathlib import Path

import pandas as pd
import yaml

CFG = Path("configs/f3/f3_4a_controlled_cal_execution_contract_v1.yaml")
PLAN = Path("docs/F3_4A_CANDIDATE_EXECUTION_PLAN_v1.csv")
INPUTS = Path("docs/F3_4A_CAL_INPUT_MANIFEST_v1.csv")
REGISTRY = Path("docs/F3_3_CANDIDATE_ARTIFACT_REGISTRY_v1.csv")


def cfg():
    return yaml.safe_load(CFG.read_text(encoding="utf-8"))


def test_contract_does_not_open_cal_or_test():
    c = cfg()
    assert c["boundary_at_f3_4a"]["cal_rows_read"] == 0
    assert c["boundary_at_f3_4a"]["candidate_selection"] == "NONE"
    assert c["boundary_at_f3_4a"]["test_partition"] == "SEALED"
    assert c["boundary_at_f3_4a"]["test_rows_read"] == 0


def test_one_component_at_a_time_and_first_is_participation():
    c = cfg()
    assert c["run_governance"]["granularity"] == "ONE_COMPONENT_AT_A_TIME"
    assert c["run_governance"]["stop_after_each_component"] is True
    assert c["run_governance"]["main_review_required_before_next_component"] is True
    assert c["run_governance"]["first_component_run"] == "DG_PARTICIPATION"
    assert c["first_controlled_run"]["downstream_components_authorized_in_same_run"] is False


def test_candidate_plan_matches_frozen_registry():
    plan = pd.read_csv(PLAN, dtype=str)
    registry = pd.read_csv(REGISTRY, dtype=str)
    assert len(plan) == len(registry) == 31
    assert set(plan["artifact_id"]) == set(registry["artifact_id"])
    assert set(registry["train_state"]) == {"FITTED_TRAIN_ONLY_NOT_SELECTED"}
    assert plan.groupby("component").size().to_dict() == {
        "DG_PARTICIPATION": 8,
        "DG_TRIP_COUNT": 5,
        "DG_ACTIVITY_CHAIN": 6,
        "DG_TIME_SCHEDULE": 7,
        "DG_DISTANCE_PRIOR": 5,
    }


def test_participation_is_only_first_execution_stage():
    plan = pd.read_csv(PLAN, dtype=str)
    first = plan[plan["execution_stage"] == "FIRST_CONTROLLED_CAL_RUN"]
    assert len(first) == 8
    assert set(first["component"]) == {"DG_PARTICIPATION"}
    assert set(first["evaluation_modes"]) == {"ISOLATED"}
    blocked = plan[plan["execution_stage"] != "FIRST_CONTROLLED_CAL_RUN"]
    assert set(blocked["execution_stage"]) == {"BLOCKED_UNTIL_PREVIOUS_COMPONENT_CLOSED"}


def test_cal_input_manifest_is_calibration_only_and_has_frozen_counts():
    inputs = pd.read_csv(INPUTS)
    assert set(inputs["partition"]) == {"CALIBRATION"}
    assert inputs.set_index("filename")["expected_rows"].to_dict() == {
        "person_day_context.csv": 469,
        "participation.csv": 460,
        "trip_count.csv": 381,
        "chain_days.csv": 319,
        "chain_transitions.csv": 1065,
        "time_trips.csv": 1243,
        "distance_raw.csv": 1147,
        "distance_expanded_sensitivity.csv": 1257,
    }


def test_frozen_protocol_constants():
    c = cfg()
    assert c["cal_session"]["scenario_id"] == "CAL_EVAL_V1"
    assert c["cal_session"]["master_seed"] == 20260926
    assert c["cal_session"]["stochastic_replicates"] == 32
    assert c["cal_session"]["household_bootstrap_replicates"] == 1000
    assert c["selection_mechanics"]["complexity_order"] == [
        "REFERENCE_BASELINE", "CORE_CANDIDATE_A", "CORE_CHALLENGER_B"
    ]


def test_primary_metrics_and_margins_are_frozen():
    c = cfg()
    assert c["promotion_margins"] == {
        "DG_PARTICIPATION": 0.005,
        "DG_TRIP_COUNT": 0.05,
        "DG_ACTIVITY_CHAIN": 0.01,
        "DG_TIME_SCHEDULE": 0.005,
        "DG_DISTANCE_PRIOR": 0.25,
    }
    assert c["primary_metrics"]["DG_PARTICIPATION"] == "WEIGHTED_BERNOULLI_LOG_LOSS"
    assert c["primary_metrics"]["DG_TRIP_COUNT"] == "WEIGHTED_DISCRETE_CRPS_ON_K"


def test_participation_point_estimation_is_preregistered():
    c = cfg()
    p = c["point_estimation"]
    assert p["participation_primary"] == "DIRECT_WEIGHTED_LOGLOSS_FROM_PROBABILITY"
    assert p["participation_share_guardrails"] == "MEAN_OF_32_STOCHASTIC_REALIZATION_METRICS"


def test_part_b_calibration_is_post_selection_only():
    c = cfg()["part_b_calibration"]
    assert c["options"] == ["NONE", "WEIGHTED_SIGMOID"]
    assert c["folds"] == 5
    assert c["cannot_rescue_nonselected_part_b"] is True
    assert c["timing"] == "ONLY_AFTER_PART_B_GRID_AND_COMPONENT_FAMILY_GRID_SELECTION"


def test_test_never_authorized_by_component_contract():
    c = cfg()
    assert c["first_controlled_run"]["test_authorized"] is False
    assert c["joint_cal_gate"]["test_open_only_if_pass"] is True
    assert c["joint_cal_gate"]["formal_g2_after_pass"] == "NOT_EVALUATED"


def test_f33a_final_remediation_hashes_are_frozen():
    c = cfg()
    assert c["candidate_registry"]["sha256"] == (
        "52328037d9a57866b188166373f798da4fb97460fc794748f8f0ef3968e86ad8"
    )
    assert c["frozen_witnesses"]["f3_3a_core"]["sha256"] == (
        "a5aa251d2e215540d7b05942b38ae35f0f5d07823ffae637e85cbe82234c2a6d"
    )


def test_human_contract_registry_hash_matches_frozen_yaml():
    c = cfg()
    contract = Path("docs/F3_4A_CONTROLLED_CAL_EXECUTION_CONTRACT_v1.md").read_text(
        encoding="utf-8"
    )
    expected = c["candidate_registry"]["sha256"]
    assert expected in contract
    assert "14280b82fab60248e955fe6e5fc1ef45e487440021f0b1d424daca935c91cd9b" not in contract
