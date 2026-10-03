import json
from pathlib import Path

import pandas as pd
import pytest
import yaml

from simfleet_edg.repro.f3_4g2e_test_auth import (
    TestAuthorizationError as HeldoutAuthorizationError,
)
from simfleet_edg.repro.f3_4g2e_test_auth import (
    load_heldout_test_authorization,
)

ROOT = Path(__file__).resolve().parents[1]
CFG = ROOT / "configs/f3/f3_4g2e_heldout_test_protocol_preopen_v1.yaml"
TEMPLATE = ROOT / "configs/f3/f3_4g2e_test_authorization_TEMPLATE_v1.json"
MATRIX = ROOT / "docs/F3_4G1_JOINT_METRIC_MATRIX_v1.csv"
SPLIT = ROOT / "artifacts/runs/R2_eligibility_split_v1/split_manifest_reproduced.csv"


def load_cfg() -> dict:
    return yaml.safe_load(CFG.read_text(encoding="utf-8"))


def test_parent_and_zero_test_outcome_state() -> None:
    cfg = load_cfg()
    assert cfg["required_parent_commit"] == "5992cdc34cd0e729a71e790caa15d839db99475d"
    assert cfg["heldout_test"]["outcome_content_rows_read_in_preopen"] == 0
    assert cfg["preopen_boundaries"]["test_open_authorized"] is False
    assert cfg["preopen_boundaries"]["holdout_consumed"] is False


def test_split_manifest_identity_is_frozen() -> None:
    cfg = load_cfg()["heldout_split_identity"]
    assert cfg["path"] == "artifacts/runs/R2_eligibility_split_v1/split_manifest_reproduced.csv"
    assert cfg["sha256"] == "5d0d4f2a41bc93b131de96d85192d8ff7002878e28e87515a0f88cedf1cebde8"
    assert cfg["split_seed"] == 20260912
    assert cfg["split_unit"] == "HOUSEHOLD"


def test_full_and_strict_split_counts() -> None:
    split = pd.read_csv(SPLIT)
    full = split["split"].astype(str).value_counts().to_dict()
    strict = split.loc[split["split_stratum"].astype(str).str.startswith("STRICT_RMIN_DONOR|")]
    strict_counts = strict["split"].astype(str).value_counts().to_dict()
    assert full == {"TRAIN": 1238, "CALIBRATION": 268, "TEST": 264}
    assert len(strict) == 1742
    assert strict_counts == {"TRAIN": 1219, "CALIBRATION": 263, "TEST": 260}


def test_household_atomic_manifest() -> None:
    split = pd.read_csv(SPLIT)
    assert len(split) == 1770
    assert split["source_household_id"].nunique(dropna=False) == 1770
    assert set(split["split_unit"].astype(str)) == {"HOUSEHOLD"}


def test_exact_eight_logical_test_inputs() -> None:
    inputs = load_cfg()["heldout_test"]["logical_inputs"]
    assert len(inputs) == 8
    assert set(inputs) == {
        "person_day_context.csv", "participation.csv", "trip_count.csv",
        "chain_days.csv", "chain_transitions.csv", "time_trips.csv",
        "distance_raw.csv", "distance_expanded_sensitivity.csv",
    }


def test_test_outcomes_not_materialized_or_read_preopen() -> None:
    heldout = load_cfg()["heldout_test"]
    assert heldout["materialized_directory_required_in_preopen"] is False
    assert heldout["materialization_deferred_until_authorized_runner"] is True
    assert heldout["outcome_content_hashes_computed_in_preopen"] is False
    assert heldout["outcome_exact_row_counts_read_in_preopen"] is False


def test_single_use_rule_is_outcome_content_bound() -> None:
    heldout = load_cfg()["heldout_test"]
    assert heldout["single_use_holdout"] is True
    assert heldout["consumed_once_any_outcome_content_is_read"] is True
    assert heldout["split_assignment_metadata_does_not_consume_holdout"] is True
    assert heldout["same_holdout_rerun_after_outcome_content_io"] is False


def test_metric_matrix_shape_is_frozen() -> None:
    matrix = pd.read_csv(MATRIX)
    decision = matrix.loc[matrix["decision_role"].ne("REPORT_ONLY")]
    report = matrix.loc[matrix["decision_role"].eq("REPORT_ONLY")]
    assert len(matrix) == 17
    assert len(decision) == 14
    assert len(report) == 3


def test_test_seed_and_crn_are_frozen() -> None:
    protocol = load_cfg()["stochastic_protocol"]
    assert protocol["replicates"] == 32
    assert protocol["master_seed"] == 20261003
    assert protocol["common_random_numbers"] is True
    assert protocol["same_seed_schedule_across_pipelines"] is True


def test_no_selection_or_post_test_tuning() -> None:
    pipelines = load_cfg()["pipelines"]
    assert pipelines["candidate_selection"] == "NONE"
    assert pipelines["post_test_tuning"] == "FORBIDDEN"
    assert pipelines["teacher_forcing"] is False


def test_formal_g2_rule_is_noncompensatory() -> None:
    cfg = load_cfg()
    assert cfg["metric_protocol"]["no_composite_score"] is True
    assert cfg["formal_g2_protocol"]["fail_if_valid_execution_and_any_decision_condition_fails"] is True


def test_tracked_authorization_template_is_negative() -> None:
    payload = json.loads(TEMPLATE.read_text(encoding="utf-8"))
    assert payload["heldout_test_open_authorized"] is False
    assert payload["formal_g2_evaluation_authorized"] is False
    assert payload["post_test_tuning_authorized"] is False
    assert payload["same_holdout_rerun_after_content_io"] is False


def test_negative_authorization_is_rejected() -> None:
    with pytest.raises(HeldoutAuthorizationError):
        load_heldout_test_authorization(TEMPLATE, ROOT)


def test_g2_remains_not_evaluated() -> None:
    assert load_cfg()["preopen_boundaries"]["formal_g2"] == "NOT_EVALUATED"
