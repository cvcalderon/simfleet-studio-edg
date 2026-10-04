import json
from pathlib import Path

import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[1]
CFG = ROOT / "configs/f1/f1_pconstr_impl01_a1_freeze_v1.yaml"
AUDIT = ROOT / "docs/F1_PCONSTR_IMPL01_A1_MAIN_AUDIT_v1.json"
SNAPSHOT = ROOT / "docs/F1_PCONSTR_IMPL01_RECONCILIATION_A1_SNAPSHOT_v1.csv"


def load_cfg() -> dict:
    return yaml.safe_load(CFG.read_text(encoding="utf-8"))


def test_freeze_status_and_commit() -> None:
    cfg = load_cfg()
    assert cfg["status_after_commit"] == "IMPL01_A1_CLOSED_FROZEN"
    assert cfg["required_parent_commit"] == "2b08eeb1440c1fd8171917b91047b1b0c6be46f6"


def test_runbundle_identity() -> None:
    source = load_cfg()["source_runbundle"]
    assert source["zip_sha256"] == "de4e70a07483f594053c2bb6b04e82e8be8d38191e0336bebad3e38186175de0"
    assert source["execution_status"] == "PASS"


def test_reconciliation_frozen_anchors() -> None:
    r = load_cfg()["reconciliation"]
    assert r["person_domain_total"] == 3532081
    assert r["bezirk_count"] == 12
    assert r["detail_cells"] == 1584
    assert r["detail_cells_changed"] == 56
    assert r["stage1_l1_total"] == 161
    assert r["stage2_l1_total"] == 272
    assert r["stage3_l1_total"] == 478
    assert r["max_detailed_abs_adjustment"] == 12
    assert r["published_zero_violations"] == 0
    assert r["all_bezirke_feasible"] is True


def test_source_row_counts() -> None:
    counts = load_cfg()["source_evidence"]["normalized_rows_by_table"]
    assert counts == {
        "1000A-1029": 84,
        "1000A-2070": 840,
        "1000A-2071": 252,
        "1000A-3082": 3024,
        "5000H-1001": 84,
    }


def test_main_audit_pass() -> None:
    audit = json.loads(AUDIT.read_text(encoding="utf-8"))
    assert audit["status"] == "PASS"
    assert audit["decision"] == "ACCEPT_FOR_MAIN_FREEZE"
    assert audit["independent_rederivation"]["aggregate_divisibility_violations_sizes_1_to_5"] == 0


def test_snapshot_has_12_feasible_bezirke() -> None:
    df = pd.read_csv(SNAPSHOT)
    assert len(df) == 12
    assert df["feasible"].all()
    assert int(df["stage1_detail_l1_optimum"].sum()) == 161
    assert int(df["stage2_hhsize_margin_l1_optimum_given_stage1"].sum()) == 272
    assert int(df["stage3_sex_hhsize_margin_l1_optimum_given_stage1_2"].sum()) == 478


def test_boundaries_remain_closed() -> None:
    b = load_cfg()["boundaries"]
    assert b["calibration_read"] is False
    assert b["test_read"] is False
    assert b["holdout_1000A_1035_read"] is False
    assert b["f3_modified"] is False


def test_project_gate_state() -> None:
    g = load_cfg()["project_gates"]
    assert g["G1"] == "OPEN"
    assert g["G2"] == "PASS_CLOSED_DO_NOT_REOPEN"
