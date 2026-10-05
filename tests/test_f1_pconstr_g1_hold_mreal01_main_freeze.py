import json
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
CFG = ROOT / "configs/f1/f1_pconstr_g1_hold_mreal01_main_freeze_v1.yaml"
AUDIT = ROOT / "docs/F1_PCONSTR_G1_HOLD_MREAL01_MAIN_AUDIT_v1.json"
CORE = ROOT / "docs/F1_PCONSTR_G1_HOLD_MREAL01_CORE_HASHES_A1_SNAPSHOT_v1.json"
MANIFEST = ROOT / "docs/F1_PCONSTR_G1_HOLD_MREAL01_RUN_MANIFEST_A1_SNAPSHOT_v1.json"


def test_freeze_parent_and_status():
    cfg = yaml.safe_load(CFG.read_text(encoding="utf-8"))
    assert cfg["required_parent_commit"] == "57891354e314df7bb38cd5b3f9e020f762826c49"
    assert cfg["status_after_commit"] == "HOLD_MREAL_001_RESOLVED_FROZEN"


def test_realization_identity_is_exact():
    cfg = yaml.safe_load(CFG.read_text(encoding="utf-8"))
    r = cfg["realization"]
    assert r["selected_candidate"] == "P_CONSTR_RMIN_V2_HD_U"
    assert r["scale_id"] == "M"
    assert r["candidate_master_seed"] == 20261005
    assert r["h6_master_seed"] == 20261004


def test_runbundle_identity_is_exact():
    cfg = yaml.safe_load(CFG.read_text(encoding="utf-8"))
    rb = cfg["source_runbundle"]
    assert rb["zip_sha256"] == "00b440d58b2c4f7f5484e8260a43f1fb9f2ce69c0b5d5c23a6272aa3b2afa505"
    assert rb["zip_size_bytes"] == 10345871
    assert rb["zip_file_count"] == 12


def test_anchor_counts_are_exact():
    cfg = yaml.safe_load(CFG.read_text(encoding="utf-8"))
    a = cfg["anchors"]
    assert a["persons"] == 100000
    assert a["households"] == 54828
    assert a["strict_persons"] == 93127
    assert a["six_plus_persons"] == 6873
    assert a["strict_households"] == 54026
    assert a["six_plus_households"] == 802
    assert a["target_fit_l1"] == 3172
    assert a["target_fit_max_abs"] == 40


def test_core_hashes_have_exact_seven_keys():
    core = json.loads(CORE.read_text(encoding="utf-8"))
    assert set(core) == {
        "households", "persons", "resources", "projected_cube_M",
        "h6_households_M", "equivalence_plan_M", "equivalence_class_fit_M",
    }
    assert len(set(core.values())) == 7


def test_manifest_preserves_holdout_boundary():
    m = json.loads(MANIFEST.read_text(encoding="utf-8"))
    assert m["holdout_1000A_1035_acquired"] is False
    assert m["holdout_1000A_1035_values_read"] is False
    assert m["holdout_metric_evaluation"] is False
    assert m["hold_thresh_001"] == "OPEN"


def test_freeze_boundary_keeps_other_lanes_closed():
    cfg = yaml.safe_load(CFG.read_text(encoding="utf-8"))
    b = cfg["boundaries"]
    assert b["holdout_1000A_1035_authorized"] is False
    assert b["cal_reopened"] is False
    assert b["mid_test_reopened"] is False
    assert b["spatial_plr_allocation"] is False
    assert b["f3_modified"] is False
    assert b["G1"] == "OPEN"
    assert b["G2"] == "PASS_CLOSED_DO_NOT_REOPEN"


def test_main_audit_accepts_only_mreal():
    a = json.loads(AUDIT.read_text(encoding="utf-8"))
    assert a["status"] == "PASS"
    assert a["decision"] == "ACCEPT_FOR_MAIN_FREEZE"
    assert a["boundaries"]["HOLD_THRESH_001"] == "OPEN"
