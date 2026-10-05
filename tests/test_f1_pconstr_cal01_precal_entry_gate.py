import json
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
GATE = ROOT / "configs/f1/f1_pconstr_cal01_precal_entry_gate_v1.yaml"
PREOPEN = ROOT / "configs/f1/f1_pconstr_cal01_preopen_v1.yaml"
AUTH = ROOT / "docs/F1_PCONSTR_CAL01_AUTHORIZATION_TEMPLATE_v1.json"


def test_entry_gate_keeps_cal_closed() -> None:
    gate = yaml.safe_load(GATE.read_text(encoding="utf-8"))
    b = gate["controlled_lineage_boundary"]
    assert b["calibration_authorized"] is False
    assert b["calibration_rows_read"] == 0
    assert b["candidate_selection"] == "NONE"
    assert b["g1_thresholds_v1"] == "NOT_FROZEN"
    assert b["mid_test_read"] is False
    assert b["holdout_1000A_1035_read"] is False
    assert b["spatial_plr_allocation"] is False
    assert b["f3_modified"] is False


def test_entry_gate_matches_preopen_boundary() -> None:
    gate = yaml.safe_load(GATE.read_text(encoding="utf-8"))
    preopen = yaml.safe_load(PREOPEN.read_text(encoding="utf-8"))
    assert gate["controlled_lineage_boundary"] == preopen["cal_boundary"]


def test_authorization_remains_unbound_and_false() -> None:
    auth = json.loads(AUTH.read_text(encoding="utf-8"))
    assert auth["authorized"] is False
    assert auth["required_precal_commit"] is None
    assert auth["authorization_status"] == "TEMPLATE_ONLY_NOT_AUTHORIZED"


def test_candidate_universe_is_exact() -> None:
    gate = yaml.safe_load(GATE.read_text(encoding="utf-8"))
    assert gate["candidate_universe"] == [
        "P_TRS_V1_FINAL",
        "P_CONSTR_RMIN_V2_HD_U",
        "P_CONSTR_RMIN_V2_HD_W",
    ]


def test_threshold_protocol_is_frozen_symbolically() -> None:
    t = yaml.safe_load(GATE.read_text(encoding="utf-8"))["threshold_protocol"]
    assert t["bootstrap_replicates"] == 1000
    assert t["confidence_quantile"] == 0.95
    assert t["quantile_method"] == "higher"
    assert t["master_seed"] == 20261005
    assert t["substream_key"] == "F1_PCONSTR_CAL_MATERIALITY_V1"


def test_authorization_must_bind_to_future_gate_commit() -> None:
    p = yaml.safe_load(GATE.read_text(encoding="utf-8"))["entry_gate_policy"]
    assert p["authorization_binding_state"] == "UNBOUND_PENDING_ENTRY_GATE_COMMIT"
    assert p["next_authorization_must_bind_to_entry_gate_commit"] is True
    assert p["cal_reader_allowed_in_this_subphase"] is False
    assert p["numeric_thresholds_allowed_in_this_subphase"] is False
    assert p["candidate_selection_allowed_in_this_subphase"] is False
