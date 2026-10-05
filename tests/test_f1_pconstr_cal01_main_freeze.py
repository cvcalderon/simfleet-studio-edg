from __future__ import annotations

import csv
import json
from decimal import Decimal
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]

def test_freeze_config_boundaries():
    cfg = yaml.safe_load((ROOT / "configs/f1/f1_pconstr_cal01_main_freeze_v1.yaml").read_text())
    assert cfg["status_after_commit"] == "CAL01_A1_CLOSED_FROZEN"
    assert cfg["selection_freeze"]["selected_candidate"] == "P_CONSTR_RMIN_V2_HD_U"
    assert cfg["boundaries"]["G1"] == "OPEN"
    assert cfg["boundaries"]["G2"] == "PASS_CLOSED_DO_NOT_REOPEN"
    assert cfg["boundaries"]["holdout_1000A_1035_read"] is False
    assert cfg["boundaries"]["holdout_1000A_1035_authorized"] is False
    assert cfg["boundaries"]["cal_reuse_as_independent_validation"] is False

def test_cal_reference_counts():
    cfg = yaml.safe_load((ROOT / "configs/f1/f1_pconstr_cal01_main_freeze_v1.yaml").read_text())
    ref = cfg["cal_reference"]
    assert ref == {
        "universe":"PRIVATE_HOUSEHOLDS",
        "split_cal_households_all":268,
        "split_cal_households_strict":263,
        "private_cal_households_materialized":267,
        "private_cal_person_rows_materialized":470,
        "test_rows_materialized":0,
    }

def test_thresholds_exact():
    rows = list(csv.DictReader((ROOT / "docs/F1_PCONSTR_G1_THRESHOLDS_v1.csv").open()))
    tau = {r["family_id"]: Decimal(r["tau"]) for r in rows}
    assert tau == {
        "ACTIVITY_BY_AGE": Decimal("0.07293353416541049"),
        "LICENSE_BY_AGE_SEX": Decimal("0.0815667541845037"),
        "HH_CAR_STOCK_BY_SIZE": Decimal("0.0660999637102583"),
        "HH_BIKE_EBIKE_STOCK_BY_SIZE": Decimal("0.07409481595332659"),
    }
    assert all(r["status"] == "FROZEN" for r in rows)

def test_selection_freeze():
    s = json.loads((ROOT / "docs/F1_PCONSTR_CAL01_SELECTION_v1.json").read_text())
    assert s["status"] == "FROZEN_BY_MAIN"
    assert s["selected_candidate"] == "P_CONSTR_RMIN_V2_HD_U"
    assert s["stage_1"]["decision"] == "RETAIN_INCUMBENT_HD_U"
    assert s["stage_2"]["decision"] == "SELECT_CONSTRAINED_HD_U"
    assert s["holdout_1000A_1035_read"] is False
    assert s["mid_test_reopened"] is False

def test_main_audit_pass():
    a = json.loads((ROOT / "docs/F1_PCONSTR_CAL01_MAIN_AUDIT_v1.json").read_text())
    assert a["status"] == "PASS"
    assert a["decision"] == "ACCEPT_FOR_MAIN_FREEZE"
    assert a["issues_count"] == 0
    assert a["independent_selection_rederivation"]["matches_runbundle_proposal"] is True
    assert a["boundaries_after_freeze"]["G1"] == "OPEN"
