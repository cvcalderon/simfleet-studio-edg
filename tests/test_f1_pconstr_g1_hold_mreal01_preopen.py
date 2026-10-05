import json
from pathlib import Path

import pytest
import yaml

from simfleet_edg.repro.f1_pconstr_g1_hold_mreal01_runner import (
    SCALE,
    SELECTED,
    validate_execution_authorization,
)

ROOT = Path(__file__).resolve().parents[1]
CFG = ROOT / "configs/f1/f1_pconstr_g1_hold_mreal01_preopen_v1.yaml"
AUTH = ROOT / "docs/F1_PCONSTR_G1_HOLD_MREAL01_EXECUTION_AUTHORIZATION_TEMPLATE_v1.json"


def test_mreal_config_is_selected_M_only():
    cfg = yaml.safe_load(CFG.read_text(encoding="utf-8"))
    assert cfg["execution_realization"]["selected_candidate"] == SELECTED
    assert cfg["execution_realization"]["scale_id"] == SCALE
    assert cfg["execution_realization"]["candidate_master_seed"] == 20261005
    assert cfg["execution_realization"]["h6_master_seed"] == 20261004


def test_frozen_M_anchors_are_exact():
    e = yaml.safe_load(CFG.read_text(encoding="utf-8"))["expected_M_materialization"]
    assert e["persons"] == 100000
    assert e["strict_persons"] == 93127
    assert e["six_plus_persons"] == 6873
    assert e["strict_households"] == 54026
    assert e["six_plus_households"] == 802
    assert e["households"] == 54828
    assert e["target_fit_l1"] == 3172
    assert e["target_fit_max_abs"] == 40
    assert e["equivalence_classes_used"] == 241


def test_holdout_boundaries_stay_closed():
    b = yaml.safe_load(CFG.read_text(encoding="utf-8"))["boundaries"]
    assert b["holdout_1000A_1035_acquired"] is False
    assert b["holdout_1000A_1035_values_read"] is False
    assert b["holdout_1000A_1035_authorized"] is False
    assert b["holdout_metric_evaluation"] is False
    assert b["holdout_threshold_tuning"] is False


def test_cal_test_plr_f3_stay_closed():
    b = yaml.safe_load(CFG.read_text(encoding="utf-8"))["boundaries"]
    assert b["cal_reopened"] is False
    assert b["mid_test_reopened"] is False
    assert b["mid_test_global_state"] == "CONSUMED_BY_G2_DO_NOT_REOPEN"
    assert b["spatial_plr_allocation"] is False
    assert b["f3_modified"] is False


def test_execution_authorization_template_is_negative():
    a = json.loads(AUTH.read_text(encoding="utf-8"))
    assert a["authorized"] is False
    assert a["mreal_execution_authorized"] is False
    assert a["authorized_runner_commit"] is None
    assert a["required_preopen_commit"] is None
    assert a["holdout_value_io_authorized"] is False
    assert a["holdout_metric_evaluation_authorized"] is False


def test_negative_template_rejected_before_execution(monkeypatch):
    values = {
        ("rev-parse", "HEAD"): "abc",
        ("rev-parse", "origin/main"): "abc",
        ("branch", "--show-current"): "main",
        ("status", "--porcelain"): "",
    }
    from simfleet_edg.repro import f1_pconstr_g1_hold_mreal01_runner as runner
    monkeypatch.setattr(runner, "_git", lambda root, *args: values[args])
    with pytest.raises(PermissionError):
        validate_execution_authorization(AUTH, ROOT)


def test_no_holdout_source_path_is_configured():
    cfg = yaml.safe_load(CFG.read_text(encoding="utf-8"))
    text = json.dumps(cfg)
    boundaries = cfg["boundaries"]

    assert "holdout_1000A_1035_acquired" in boundaries
    assert "holdout_1000A_1035_values_read" in boundaries
    assert "holdout_1000A_1035_authorized" in boundaries
    assert "source_path" not in text
    assert "download" not in text.lower()


def test_output_contract_requires_core_hashes():
    c = yaml.safe_load(CFG.read_text(encoding="utf-8"))["output_contract"]
    assert c["freeze_role_after_MAIN_audit"] == "M_REALIZATION_CORE_HASHES_FROZEN"
    assert set(c["core_hashes_required"]) >= {
        "households", "persons", "resources", "projected_cube_M",
        "h6_households_M", "equivalence_plan_M"
    }
