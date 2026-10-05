import json
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def test_cal01_config_keeps_cal_closed() -> None:
    cfg = yaml.safe_load((ROOT / "configs/f1/f1_pconstr_cal01_preopen_v1.yaml").read_text())
    b = cfg["cal_boundary"]
    assert b["calibration_rows_read"] == 0
    assert b["calibration_authorized"] is False
    assert b["candidate_selection"] == "NONE"
    assert b["g1_thresholds_v1"] == "NOT_FROZEN"
    assert b["mid_test_read"] is False
    assert b["holdout_1000A_1035_read"] is False
    assert b["G1"] == "OPEN"
    assert b["G2"] == "PASS_CLOSED_DO_NOT_REOPEN"


def test_candidate_universe_exact() -> None:
    cfg = yaml.safe_load((ROOT / "configs/f1/f1_pconstr_cal01_preopen_v1.yaml").read_text())
    c = cfg["candidate_universe"]
    assert [c["baseline"], c["constrained_incumbent"], c["constrained_challenger"]] == [
        "P_TRS_V1_FINAL", "P_CONSTR_RMIN_V2_HD_U", "P_CONSTR_RMIN_V2_HD_W"
    ]


def test_authorization_is_template_only() -> None:
    payload = json.loads((ROOT / "docs/F1_PCONSTR_CAL01_AUTHORIZATION_TEMPLATE_v1.json").read_text())
    assert payload["authorized"] is False
    assert payload["required_precal_commit"] is None
    assert payload["authorization_status"] == "TEMPLATE_ONLY_NOT_AUTHORIZED"
