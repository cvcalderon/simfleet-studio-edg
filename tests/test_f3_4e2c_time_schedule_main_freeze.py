import json
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
CFG = ROOT / "configs/f3/f3_4e2c_time_schedule_main_freeze_v1.yaml"
SEL = ROOT / "configs/f3/f3_4e2c_selected_time_schedule_artifact_v1.json"


def test_selected_artifact_is_tb2():
    selected = json.loads(SEL.read_text(encoding="utf-8"))
    assert selected["artifact_id"] == "TIME_B_TB2"
    assert selected["candidate_id"] == "TIME_B"
    assert selected["grid_id"] == "TB2"


def test_selected_artifact_state_is_main_frozen_and_runtime_authorized():
    selected = json.loads(SEL.read_text(encoding="utf-8"))
    assert selected["state"] == "MAIN_FROZEN"
    assert selected["authorized_for_runtime_dgen"] is True


def test_selected_artifact_hashes_are_exact():
    selected = json.loads(SEL.read_text(encoding="utf-8"))
    assert selected["model_sha256"] == "74aa012647291854c4fa087f1dd798e9d909e3c681046f1447307a23a6d5f900"
    assert selected["manifest_sha256"] == "ff3caa54e7ee11c2bde79e49da5604277d506c826b891fb7a1e4edd04b157c5a"


def test_primary_and_promotion_are_frozen():
    cfg = yaml.safe_load(CFG.read_text(encoding="utf-8"))
    assert cfg["primary_metric"]["metric"] == "M2-TIME-01"
    assert cfg["primary_metric"]["practical_margin"] == 0.005
    assert cfg["promotion"]["challenger"] == "TIME_B_TB2"
    assert cfg["promotion"]["promoted"] is True
    assert cfg["promotion"]["bootstrap_ci95_lower_reported"] > 0


def test_isolated_and_propagated_hard_guardrails_pass():
    cfg = yaml.safe_load(CFG.read_text(encoding="utf-8"))
    assert cfg["isolated_guardrails"]["pass"] is True
    assert cfg["propagated_guardrails"]["conjunctive_pass"] is True
    assert cfg["propagated_guardrails"]["TIME_REF_REFERENCE"]["temporal_invariant_violations"] == 0
    assert cfg["propagated_guardrails"]["TIME_B_TB2"]["temporal_invariant_violations"] == 0


def test_full_chain_sampling_policies_are_frozen():
    cfg = yaml.safe_load(CFG.read_text(encoding="utf-8"))
    assert cfg["sampling_policy"]["propagated_time_b"] == "EXACT_TIME_B_FULL_CHAIN_MIN_SLACK_CONDITIONAL_V1"
    assert cfg["sampling_policy"]["propagated_time_ref"] == "EXACT_REFERENCE_FULL_CHAIN_SUPPORT_CONDITIONAL_V1"


def test_downstream_boundaries_remain_closed():
    cfg = yaml.safe_load(CFG.read_text(encoding="utf-8"))
    selected = json.loads(SEL.read_text(encoding="utf-8"))
    assert cfg["boundaries"]["next_component_authorized"] is False
    assert cfg["boundaries"]["distance_prior_real_cal_authorized"] is False
    assert selected["distance_prior_real_cal_authorized"] is False
    assert selected["test_open_authorized"] is False
    assert selected["formal_g2"] == "NOT_EVALUATED"
