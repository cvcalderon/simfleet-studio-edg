import json
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
CFG = ROOT / "configs/f3/f3_4d2c_activity_chain_main_freeze_v1.yaml"
SEL = ROOT / "configs/f3/f3_4d2c_selected_activity_chain_artifact_v1.json"


def test_selected_artifact_is_cha2():
    selected = json.loads(SEL.read_text(encoding="utf-8"))
    assert selected["artifact_id"] == "DG_ACTIVITY_CHAIN::CHAIN_A::CHA2"
    assert selected["candidate_id"] == "CHAIN_A"
    assert selected["grid_id"] == "CHA2"


def test_selected_artifact_state_is_main_frozen():
    selected = json.loads(SEL.read_text(encoding="utf-8"))
    assert selected["state"] == "MAIN_FROZEN"
    assert selected["authorized_for_runtime_dgen"] is True


def test_selected_artifact_hashes_are_exact():
    selected = json.loads(SEL.read_text(encoding="utf-8"))
    assert selected["model_sha256"] == "242085ebab9eb5ec8a53ea3b8ffe65c1d1e1fdb660bcacff0ab172d1b5ef1ecf"
    assert selected["manifest_sha256"] == "337140dd45522a47659603998838a3c869646cbd70961ba874d6f34be555ea73"
    assert selected["purpose_artifact_sha256"] == "ab42cf42c9568ef4f085f071299fc941d421c42337f353e00870cd05c94f94fb"


def test_primary_and_promotion_are_frozen():
    cfg = yaml.safe_load(CFG.read_text(encoding="utf-8"))
    assert cfg["primary_metric"]["metric"] == "WEIGHTED_NEXT_ACTIVITY_LOG_LOSS"
    assert cfg["primary_metric"]["practical_margin"] == 0.01
    assert cfg["promotion"]["challenger"] == "DG_ACTIVITY_CHAIN::CHAIN_A::CHA2"
    assert cfg["promotion"]["promoted"] is True
    assert cfg["promotion"]["bootstrap_ci95_lower"] > 0


def test_isolated_and_propagated_guardrails_pass():
    cfg = yaml.safe_load(CFG.read_text(encoding="utf-8"))
    assert cfg["isolated_guardrails"]["pass"] is True
    assert cfg["propagated_guardrails"]["pass"] is True


def test_chain_b_not_eligible_for_promotion():
    cfg = yaml.safe_load(CFG.read_text(encoding="utf-8"))
    assert all(
        entry["isolated_guardrails_pass"] is False
        for entry in cfg["challenger_b"].values()
    )


def test_downstream_boundaries_remain_closed():
    cfg = yaml.safe_load(CFG.read_text(encoding="utf-8"))
    selected = json.loads(SEL.read_text(encoding="utf-8"))
    assert cfg["boundaries"]["next_component_authorized"] is False
    assert cfg["boundaries"]["real_time_schedule_cal_open_authorized"] is False
    assert selected["test_open_authorized"] is False
    assert selected["formal_g2"] == "NOT_EVALUATED"
