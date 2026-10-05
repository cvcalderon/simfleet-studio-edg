import json
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
CFG = ROOT / "configs/f1/f1_pconstr_g1_holdout_1000a_1035_auth_preopen_v1.yaml"
AUTH = ROOT / "docs/F1_PCONSTR_G1_HOLDOUT_1000A_1035_EXECUTION_AUTHORIZATION_TEMPLATE_A1.json"


def load_cfg():
    return yaml.safe_load(CFG.read_text(encoding="utf-8"))


def load_auth():
    return json.loads(AUTH.read_text(encoding="utf-8"))


def test_parent_and_phase_are_exact():
    cfg = load_cfg()
    assert cfg["required_parent_commit"] == "f6b53d605f4e2ae73a1ad873838eb8cd8d8aca64"
    assert cfg["phase_id"] == "F1-P-CONSTR-G1-HOLDOUT-1000A-1035-AUTH-PREOPEN"


def test_candidate_mreal_and_threshold_are_frozen():
    lineage = load_cfg()["frozen_lineage"]
    assert lineage["selected_candidate"] == "P_CONSTR_RMIN_V2_HD_U"
    assert lineage["mreal_status"] == "RESOLVED_FROZEN"
    assert lineage["threshold_status"] == "RESOLVED_FROZEN"
    assert lineage["threshold_value"] == "0.0815667541845037"


def test_decision_metrics_are_exact():
    metrics = load_cfg()["metrics"]
    assert metrics["G1-HOLD-SEN-BERLIN-TVD"]["role"] == "DECISION"
    assert metrics["G1-HOLD-SEN-BEZ-WTVD"]["role"] == "DECISION"
    assert metrics["G1-HOLD-SEN-BEZ-MAX"]["role"] == "REPORT_ONLY"
    assert metrics["pass_requires_all_decision_metrics"] is True
    assert metrics["no_composite_score"] is True


def test_holdout_remains_closed_precommit():
    state = load_cfg()["boundaries"]
    assert state["holdout_1000A_1035_acquired"] is False
    assert state["holdout_1000A_1035_values_read"] is False
    assert state["holdout_1000A_1035_authorized"] is False
    assert state["holdout_metric_evaluation"] is False


def test_test_cal_plr_f3_remain_closed():
    state = load_cfg()["boundaries"]
    assert state["CAL"] == "CLOSED_DO_NOT_REOPEN"
    assert state["MiD_TEST"] == "CONSUMED_BY_G2_DO_NOT_REOPEN"
    assert state["spatial_plr_allocation"] is False
    assert state["f3_modified"] is False


def test_authorization_template_is_negative():
    auth = load_auth()
    assert auth["authorized"] is False
    assert auth["status"] == "TEMPLATE_NEGATIVE_NOT_AUTHORIZED"
    assert auth["required_authoritative_commit"] == "__AUTH_PREOPEN_COMMIT__"
    assert all(value is False for value in auth["authorized_actions"].values())


def test_positive_authorization_requires_exact_commit_state():
    contract = load_cfg()["positive_authorization_contract"]
    assert contract["must_bind_exact_authoritative_commit"] is True
    assert contract["must_require_branch_main"] is True
    assert contract["must_require_head_origin_equal"] is True
    assert contract["must_require_clean_worktree"] is True


def test_post_opening_tuning_is_forbidden():
    contract = load_cfg()["positive_authorization_contract"]
    assert contract["candidate_selection_during_holdout"] == "NONE"
    assert contract["threshold_tuning_after_holdout"] == "FORBIDDEN"
    assert contract["same_lineage_code_tuning_after_holdout"] == "FORBIDDEN"
    assert contract["failure_requires_new_experimental_lineage"] is True
