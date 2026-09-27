from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pandas as pd
import pytest

from simfleet_edg.evaluation.pre_cal_entry_gate import (
    PreCalGateSnapshot,
    evaluate_pre_cal_gate,
)


def _good() -> PreCalGateSnapshot:
    return PreCalGateSnapshot(
        lineage_ok=True,
        committed_overlay_checksums_ok=True,
        f3_1c_witnesses_ok=True,
        candidate_registry_ok=True,
        artifact_bytes_ok=True,
        metrics_and_margins_ok=True,
        isolated_propagated_ok=True,
        crn_and_replicates_ok=True,
        household_bootstrap_ok=True,
        part_b_crossfit_ok=True,
        promotion_logic_ok=True,
        joint_test_gate_ok=True,
        cal_access_blocked_before_gate=True,
        test_access_blocked=True,
        cal_rows_read_zero=True,
        test_rows_read_zero=True,
        selection_none=True,
        regression_evidence_ok=True,
    )


def test_all_green_authorizes_cal_but_not_test():
    decision = evaluate_pre_cal_gate(_good())
    assert decision.pass_gate is True
    assert decision.cal_open_authorized_for_next_controlled_run is True
    assert decision.test_open_authorized is False
    assert decision.formal_g2 == "NOT_EVALUATED"
    assert decision.reasons == ()


def test_candidate_registry_uses_authoritative_train_state_column():
    registry = pd.read_csv(
        Path("docs/F3_3_CANDIDATE_ARTIFACT_REGISTRY_v1.csv"),
        dtype=str,
    )
    assert len(registry) == 31
    assert "train_state" in registry.columns
    assert "status" not in registry.columns
    assert set(registry["train_state"]) == {"FITTED_TRAIN_ONLY_NOT_SELECTED"}


@pytest.mark.parametrize(
    "field,reason",
    [
        ("lineage_ok", "LINEAGE_MISMATCH"),
        ("committed_overlay_checksums_ok", "COMMITTED_OVERLAY_CHECKSUM_FAILURE"),
        ("f3_1c_witnesses_ok", "F3_1C_WITNESS_FAILURE"),
        ("candidate_registry_ok", "CANDIDATE_REGISTRY_FAILURE"),
        ("artifact_bytes_ok", "ARTIFACT_IDENTITY_FAILURE"),
        ("metrics_and_margins_ok", "METRIC_OR_MARGIN_FAILURE"),
        ("isolated_propagated_ok", "EVALUATION_MODE_FAILURE"),
        ("crn_and_replicates_ok", "CRN_OR_REPLICATION_FAILURE"),
        ("household_bootstrap_ok", "BOOTSTRAP_FAILURE"),
        ("part_b_crossfit_ok", "PART_B_CROSSFIT_FAILURE"),
        ("promotion_logic_ok", "PROMOTION_LOGIC_FAILURE"),
        ("joint_test_gate_ok", "JOINT_TEST_GATE_FAILURE"),
        ("cal_access_blocked_before_gate", "CAL_WAS_OPEN_BEFORE_GATE"),
        ("test_access_blocked", "TEST_NOT_SEALED"),
        ("cal_rows_read_zero", "CAL_ROWS_ALREADY_READ"),
        ("test_rows_read_zero", "TEST_ROWS_ALREADY_READ"),
        ("selection_none", "SELECTION_ALREADY_PERFORMED"),
        ("regression_evidence_ok", "REGRESSION_EVIDENCE_FAILURE"),
    ],
)
def test_each_failed_condition_blocks_cal(field: str, reason: str):
    decision = evaluate_pre_cal_gate(replace(_good(), **{field: False}))
    assert decision.pass_gate is False
    assert decision.cal_open_authorized_for_next_controlled_run is False
    assert decision.test_open_authorized is False
    assert reason in decision.reasons
