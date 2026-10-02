import json
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
CFG = ROOT / "configs/f3/f3_4f2c_distance_prior_main_freeze_v1.yaml"
SEL = ROOT / "configs/f3/f3_4f2c_selected_distance_prior_artifact_v1.json"


def test_selected_artifact_is_reference() -> None:
    selected = json.loads(SEL.read_text(encoding="utf-8"))
    assert selected["artifact_id"] == "DIST_REF_REFERENCE"
    assert selected["candidate_id"] == "DIST_REF"
    assert selected["grid_id"] == "REFERENCE"


def test_selected_artifact_is_main_frozen_and_runtime_authorized() -> None:
    selected = json.loads(SEL.read_text(encoding="utf-8"))
    assert selected["state"] == "MAIN_FROZEN"
    assert selected["authorized_for_runtime_dgen"] is True


def test_selected_artifact_hashes_are_exact() -> None:
    selected = json.loads(SEL.read_text(encoding="utf-8"))
    assert selected["model_sha256"] == (
        "21554c37d44aad7144c8daac1ddfd9e9a63402d59e105f9e790e83c1ea6e4cab"
    )
    assert selected["manifest_sha256"] == (
        "4a30ae1f586418c31a55028e2902d28c43e234a1fddaadccba9103c1a09bd409"
    )


def test_da1_is_blocked_by_p95_guardrail() -> None:
    cfg = yaml.safe_load(CFG.read_text(encoding="utf-8"))
    a = cfg["candidate_a_resolution"]
    assert a["primary_margin_pass"] is True
    assert a["guardrails_pass"] is False
    assert a["failed_guardrail"] == "P95"
    assert a["p95_worsening_km"] > a["quantile_worsening_tolerance_km"]


def test_no_challenger_reaches_bootstrap_or_promotion() -> None:
    cfg = yaml.safe_load(CFG.read_text(encoding="utf-8"))
    assert cfg["source_real_cal"]["bootstrap_replicates_preregistered"] == 1000
    assert cfg["source_real_cal"]["bootstrap_replicates_executed"] == 0
    assert cfg["candidate_a_resolution"]["promoted"] is False
    assert cfg["candidate_b_resolution"]["any_guardrail_eligible"] is False


def test_propagated_runtime_guardrail_passes() -> None:
    cfg = yaml.safe_load(CFG.read_text(encoding="utf-8"))
    propagated = cfg["propagated_guardrail"]
    assert propagated["runtime_invariant_violations"] == 0
    assert propagated["generated_distance_rows"] == 36449
    assert propagated["hard_pass"] is True


def test_semantic_boundary_is_retained() -> None:
    cfg = yaml.safe_load(CFG.read_text(encoding="utf-8"))
    boundary = cfg["semantic_boundary"]
    assert boundary["generated_distance"] == (
        "M2_PATH_LENGTH_PRIOR_FOR_M3_NOT_EXACT_OD_OR_ROUTED_DISTANCE"
    )
    assert boundary["primary_target"] == "wegkm"
    assert boundary["sensitivity_target"] == "wegkm_imp"
    assert boundary["forbidden_target"] == "km_routing"


def test_downstream_boundaries_remain_closed() -> None:
    cfg = yaml.safe_load(CFG.read_text(encoding="utf-8"))
    selected = json.loads(SEL.read_text(encoding="utf-8"))
    assert cfg["boundaries"]["all_five_dgen_components_main_frozen"] is True
    assert cfg["boundaries"]["joint_cal_gate_authorized"] is False
    assert selected["joint_cal_gate_authorized"] is False
    assert selected["test_open_authorized"] is False
    assert selected["test_rows_read"] == 0
    assert selected["formal_g2"] == "NOT_EVALUATED"
