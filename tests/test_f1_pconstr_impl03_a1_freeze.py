import json
from pathlib import Path

import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[1]
CFG = ROOT / "configs/f1/f1_pconstr_impl03_a1_freeze_v1.yaml"
AUDIT = ROOT / "docs/F1_PCONSTR_IMPL03_A1_MAIN_AUDIT_v1.json"
CAND = ROOT / "docs/F1_PCONSTR_IMPL03_CANDIDATE_SUMMARY_S_A1_SNAPSHOT_v1.csv"
MPLAN = ROOT / "docs/F1_PCONSTR_IMPL03_M_PLAN_SUMMARY_A1_SNAPSHOT_v1.csv"
VALID = ROOT / "docs/F1_PCONSTR_IMPL03_VALIDATION_A1_SNAPSHOT_v1.csv"
H6 = ROOT / "docs/F1_PCONSTR_IMPL03_SIX_PLUS_HASHES_A1_SNAPSHOT_v1.csv"
CAT = ROOT / "docs/F1_PCONSTR_IMPL03_CATALOG_SUMMARY_A1_SNAPSHOT_v1.csv"


def load_cfg() -> dict:
    return yaml.safe_load(CFG.read_text(encoding="utf-8"))


def test_freeze_status_parent_and_runbundle() -> None:
    cfg = load_cfg()
    assert cfg["status_after_commit"] == "IMPL03_A1_CLOSED_FROZEN"
    assert cfg["required_parent_commit"] == "9feb3471b8c1581b18571cbdc0b9e27001e3f632"
    assert cfg["source_runbundle"]["zip_sha256"] == "78c2a939cd7de08b048aed0cbd2a21abed73c87b68ce71860af1bbe321dd42a6"
    assert cfg["source_runbundle"]["execution_status"] == "PASS"
    assert cfg["source_runbundle"]["validation_checks"] == 33


def test_frozen_execution_scope() -> None:
    cfg = load_cfg()
    assert cfg["execution_scope"]["fully_materialized_scale"] == "S"
    assert cfg["execution_scope"]["additional_plan_only_scale"] == "M"
    assert cfg["execution_scope"]["variants"] == [
        "P_TRS_V1_FINAL", "P_CONSTR_RMIN_V2_HD_U", "P_CONSTR_RMIN_V2_HD_W"
    ]


def test_frozen_candidate_anchors_match_snapshot() -> None:
    cfg = load_cfg()
    df = pd.read_csv(CAND).set_index("variant_id")
    for variant, exp in cfg["S_anchors"].items():
        row = df.loc[variant]
        for field in ["households", "persons", "resources", "strict_households", "six_plus_households", "target_fit_l1", "target_fit_max_abs"]:
            assert int(row[field]) == int(exp[field])


def test_M_plan_anchors_match_snapshot() -> None:
    cfg = load_cfg()
    row = pd.read_csv(MPLAN).iloc[0]
    mapping = {
        "groups": "groups",
        "target_households": "target_households",
        "generated_households": "generated_households",
        "target_persons": "target_persons",
        "generated_persons": "generated_persons",
        "l1_person_cell_error": "l1_person_cell_error",
        "max_abs_person_cell_error": "max_abs_person_cell_error",
        "plan_rows": "plan_rows",
        "positive_equivalence_classes": "positive_equivalence_classes",
    }
    for cfg_field, csv_field in mapping.items():
        assert int(row[csv_field]) == int(cfg["M_plan_anchors"][cfg_field])


def test_validation_snapshot_all_pass() -> None:
    df = pd.read_csv(VALID)
    assert len(df) == 33
    assert df["status"].eq("PASS").all()


def test_common_six_plus_snapshot() -> None:
    cfg = load_cfg()
    df = pd.read_csv(H6)
    assert len(df) == 3
    assert df["signature_sha256"].nunique() == 1
    assert set(df["person_rows"]) == {685}
    assert df.iloc[0]["signature_sha256"] == cfg["six_plus"]["runbundle_signature_sha256"]


def test_catalog_snapshot() -> None:
    cfg = load_cfg()
    row = pd.read_csv(CAT).iloc[0]
    assert int(row["strict_train_households"]) == cfg["catalog"]["strict_train_households"]
    assert int(row["train_six_plus_templates"]) == cfg["catalog"]["train_six_plus_templates"]
    assert int(row["train_private_person_donors"]) == cfg["catalog"]["train_private_person_donors"]
    assert int(row["equivalence_classes"]) == cfg["catalog"]["equivalence_classes"]
    assert int(row["person_donor_support_cells"]) == cfg["catalog"]["person_donor_support_cells"]


def test_boundaries_and_gates_frozen() -> None:
    cfg = load_cfg()
    b = cfg["boundaries"]
    for key in ["calibration_read", "mid_test_read_by_impl03", "holdout_1000A_1035_read", "mobility_outcome_matching", "spatial_plr_allocation", "candidate_selection", "g1_threshold_tuning", "f3_modified"]:
        assert b[key] is False
    assert b["donor_partition"] == "TRAIN_ONLY"
    assert b["mid_test_global_state"] == "CONSUMED_BY_G2_DO_NOT_REOPEN"
    assert cfg["project_gates"]["G1"] == "OPEN"
    assert cfg["project_gates"]["G2"] == "PASS_CLOSED_DO_NOT_REOPEN"


def test_main_audit_accepts_freeze() -> None:
    audit = json.loads(AUDIT.read_text(encoding="utf-8"))
    assert audit["status"] == "PASS"
    assert audit["decision"] == "ACCEPT_FOR_MAIN_FREEZE"
    assert audit["implementation_commit"] == "9feb3471b8c1581b18571cbdc0b9e27001e3f632"
    assert audit["runbundle_zip_sha256"] == "78c2a939cd7de08b048aed0cbd2a21abed73c87b68ce71860af1bbe321dd42a6"
