import json
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
EXPECTED = "83df51a035d21621b9c5b8de04b6f03ea1a78174"

def test_authorization_is_explicit_and_bound():
    data=json.loads((ROOT/"docs/F1_PCONSTR_CAL01_AUTHORIZATION_v1.json").read_text())
    assert data["authorized"] is True
    assert data["required_precal_commit"] == EXPECTED
    assert data["allowed_partition"] == "CALIBRATION_ONLY"

def test_authorization_does_not_read_cal():
    data=json.loads((ROOT/"docs/F1_PCONSTR_CAL01_AUTHORIZATION_v1.json").read_text())
    assert data["calibration_rows_read_at_authorization"] == 0
    assert data["cal_reader_present_in_authorization_subphase"] is False

def test_selection_and_thresholds_still_deferred():
    data=json.loads((ROOT/"docs/F1_PCONSTR_CAL01_AUTHORIZATION_v1.json").read_text())
    assert data["candidate_selection_before_authorized_run"] == "NONE"
    assert data["g1_thresholds_before_authorized_run"] == "NOT_FROZEN"

def test_frozen_template_remains_false_and_unbound():
    data=json.loads((ROOT/"docs/F1_PCONSTR_CAL01_AUTHORIZATION_TEMPLATE_v1.json").read_text())
    assert data["authorized"] is False
    assert data["required_precal_commit"] is None

def test_config_matches_authorization():
    cfg=yaml.safe_load((ROOT/"configs/f1/f1_pconstr_cal01_authorization_v1.yaml").read_text())
    assert cfg["controlled_authorization"]["authorized"] is True
    assert cfg["controlled_authorization"]["required_precal_commit"] == EXPECTED
    assert cfg["controlled_authorization"]["calibration_rows_read_at_authorization"] == 0

def test_forbidden_inputs_remain_forbidden():
    data=json.loads((ROOT/"docs/F1_PCONSTR_CAL01_AUTHORIZATION_v1.json").read_text())
    forbidden=set(data["forbidden_inputs"])
    assert {"MiD TEST rows","1000A-1035","PLR target allocation inputs","F3 held-out TEST artifacts"} <= forbidden
