import json
from pathlib import Path

import pytest
import yaml

from simfleet_edg.repro.f3_4g2b_joint_real_cal_auth import (
    EXPECTED_FILES,
    EXPECTED_TOTAL_ROWS,
    AuthorizationError,
    load_joint_real_cal_authorization,
)

ROOT = Path(__file__).resolve().parents[1]
CFG = ROOT / "configs/f3/f3_4g2b_joint_real_cal_auth_preopen_v1.yaml"
TEMPLATE = ROOT / "configs/f3/f3_4g2b_joint_real_cal_authorization_TEMPLATE_v1.json"


def load_cfg() -> dict:
    return yaml.safe_load(CFG.read_text(encoding="utf-8"))


def test_exact_parent_and_zero_cal_rows() -> None:
    cfg = load_cfg()
    assert cfg["required_parent_commit"] == (
        "30c6340baccac11555800b77d12c4f6d80a89392"
    )
    assert cfg["future_real_cal"]["rows_read_in_f3_4g2b"] == 0
    assert cfg["future_real_cal"]["file_content_read_in_f3_4g2b"] is False


def test_exact_eight_allowed_cal_files_and_total() -> None:
    cfg = load_cfg()
    assert set(cfg["future_real_cal"]["allowed_files"]) == EXPECTED_FILES
    assert sum(cfg["future_real_cal"]["allowed_files"].values()) == 6341
    assert EXPECTED_TOTAL_ROWS == 6341


def test_two_pipelines_remain_five_slots_each() -> None:
    cfg = load_cfg()
    assert len(cfg["pipelines"]["selected"]) == 5
    assert len(cfg["pipelines"]["all_reference"]) == 5


def test_tracked_authorization_template_is_negative() -> None:
    template = json.loads(TEMPLATE.read_text(encoding="utf-8"))
    assert template["joint_real_cal_open_authorized"] is False
    assert template["joint_gate_evaluation_authorized"] is False
    assert template["test_open_authorized"] is False
    assert template["formal_g2"] == "NOT_EVALUATED"


def test_authorization_must_precede_cal_and_staging() -> None:
    boundary = load_cfg()["authorization_boundary"]
    assert boundary["authorization_must_precede_cal_path_open"] is True
    assert boundary["authorization_must_precede_output_staging_creation"] is True


def test_positive_authorization_must_be_external() -> None:
    boundary = load_cfg()["authorization_boundary"]
    assert boundary["positive_authorization_file_tracked_in_repo"] is False
    assert boundary["positive_authorization_file_must_be_external"] is True


def test_template_is_rejected_before_any_execution() -> None:
    with pytest.raises(AuthorizationError):
        load_joint_real_cal_authorization(TEMPLATE, ROOT)


def test_missing_authorization_is_rejected() -> None:
    with pytest.raises(AuthorizationError):
        load_joint_real_cal_authorization(
            ROOT / "does_not_exist_F3_4g2b_auth.json",
            ROOT,
        )


def test_failure_after_staging_requires_new_authorization() -> None:
    semantics = load_cfg()["failure_semantics"]
    assert semantics["failure_after_positive_authorization_and_staging"][
        "preserve_partial_runbundle"
    ] is True
    assert semantics["failure_after_positive_authorization_and_staging"][
        "rerun_same_authorization"
    ] is False


def test_test_and_g2_boundaries_remain_closed() -> None:
    boundary = load_cfg()["boundaries"]
    assert boundary["joint_real_cal_open_authorized"] is False
    assert boundary["joint_gate_evaluated"] is False
    assert boundary["test_open_authorized"] is False
    assert boundary["test_rows_read"] == 0
    assert boundary["formal_g2"] == "NOT_EVALUATED"
