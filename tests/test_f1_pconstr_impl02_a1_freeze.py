import json
from pathlib import Path

import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[1]
CFG = ROOT / "configs/f1/f1_pconstr_impl02_a1_freeze_v1.yaml"
AUDIT = ROOT / "docs/F1_PCONSTR_IMPL02_A1_MAIN_AUDIT_v1.json"
SCALE = ROOT / "docs/F1_PCONSTR_IMPL02_SCALE_SUMMARY_A1_SNAPSHOT_v1.csv"
FULL = ROOT / "docs/F1_PCONSTR_IMPL02_FULL_H6_PRIOR_A1_SNAPSHOT_v1.csv"


def load_cfg() -> dict:
    return yaml.safe_load(CFG.read_text(encoding="utf-8"))


def test_freeze_status_and_parent() -> None:
    cfg = load_cfg()
    assert cfg["status_after_commit"] == "IMPL02_A1_CLOSED_FROZEN"
    assert cfg["required_parent_commit"] == "b60017b8233856fa365bc63d4ddca9aa47e14566"


def test_runbundle_identity() -> None:
    source = load_cfg()["source_runbundle"]
    assert source["zip_sha256"] == "3a22dcf88dfbd83271d8b0b65d4d3c5590431bcf8ac269fddf713c4364474b81"
    assert source["execution_status"] == "PASS"


def test_scale_anchors() -> None:
    cfg = load_cfg()["scale_projection"]["scales"]
    assert cfg["S"] == {"target_persons": 10000, "projection_l1_scaled_numerator": 1392907648, "p6_persons_berlin": 685}
    assert cfg["M"] == {"target_persons": 100000, "projection_l1_scaled_numerator": 1360353392, "p6_persons_berlin": 6873}
    assert cfg["L"] == {"target_persons": 1000000, "projection_l1_scaled_numerator": 1326140012, "p6_persons_berlin": 68711}


def test_six_plus_anchors() -> None:
    h6 = load_cfg()["six_plus"]
    assert h6["full_scale_h6_berlin"] == 28343
    assert h6["scales"]["S"]["h6_households"] == 80
    assert h6["scales"]["M"]["h6_households"] == 802
    assert h6["scales"]["L"]["h6_households"] == 8024
    assert h6["donor_materialization"] == "DEFERRED_TO_IMPL_03"


def test_scale_snapshot_has_three_rows() -> None:
    df = pd.read_csv(SCALE)
    assert list(df["scale_id"]) == ["S", "M", "L"]
    assert list(df["target_persons"]) == [10000, 100000, 1000000]


def test_full_prior_snapshot() -> None:
    df = pd.read_csv(FULL)
    assert len(df) == 12
    assert int(df["full_scale_h6_prior"].sum()) == 28343
    assert int(df["person_target_6plus_full"].sum()) == 242676
    assert set(df["role"]) == {"MODEL_FIXED_STRUCTURAL_TARGET_NOT_SOURCE_HARD"}


def test_semantic_guardrail() -> None:
    note = load_cfg()["semantic_note"]
    assert note["published_1000A_1029_p6_persons"] == 242700
    assert note["reconciled_fullscale_p6_persons"] == 242676
    assert note["difference"] == -24
    assert note["rule"] == "SCALE_PROJECTION_USES_RECONCILED_IMPL01_CUBE_NOT_RAW_1029_MARGIN"


def test_main_audit_pass() -> None:
    audit = json.loads(AUDIT.read_text(encoding="utf-8"))
    assert audit["status"] == "PASS"
    assert audit["decision"] == "ACCEPT_FOR_MAIN_FREEZE"
    assert audit["independent_rederivation"]["scales"]["S"]["structural_zero_violations"] == 0
    assert audit["independent_rederivation"]["scales"]["L"]["divisibility_violations_sizes_1_to_5"] == 0


def test_boundaries_and_gates() -> None:
    cfg = load_cfg()
    b = cfg["boundaries"]
    assert b["calibration_read"] is False
    assert b["mid_test_read_by_impl02"] is False
    assert b["mid_test_global_state"] == "CONSUMED_BY_G2_DO_NOT_REOPEN"
    assert b["holdout_1000A_1035_read"] is False
    assert b["donor_materialization"] is False
    assert b["spatial_PLR_allocation"] is False
    assert b["candidate_HD_U_HD_W"] is False
    assert b["f3_modified"] is False
    assert cfg["project_gates"] == {"G1": "OPEN", "G2": "PASS_CLOSED_DO_NOT_REOPEN"}
