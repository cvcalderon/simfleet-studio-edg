"""Pure F3.3d PRE-CAL entry-gate decision primitive."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PreCalGateSnapshot:
    lineage_ok: bool
    committed_overlay_checksums_ok: bool
    f3_1c_witnesses_ok: bool
    candidate_registry_ok: bool
    artifact_bytes_ok: bool
    metrics_and_margins_ok: bool
    isolated_propagated_ok: bool
    crn_and_replicates_ok: bool
    household_bootstrap_ok: bool
    part_b_crossfit_ok: bool
    promotion_logic_ok: bool
    joint_test_gate_ok: bool
    cal_access_blocked_before_gate: bool
    test_access_blocked: bool
    cal_rows_read_zero: bool
    test_rows_read_zero: bool
    selection_none: bool
    regression_evidence_ok: bool


@dataclass(frozen=True)
class PreCalGateDecision:
    pass_gate: bool
    cal_open_authorized_for_next_controlled_run: bool
    test_open_authorized: bool
    formal_g2: str
    reasons: tuple[str, ...]


_CHECKS = (
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
)


def evaluate_pre_cal_gate(snapshot: PreCalGateSnapshot) -> PreCalGateDecision:
    reasons = tuple(reason for field, reason in _CHECKS if not getattr(snapshot, field))
    passed = len(reasons) == 0
    return PreCalGateDecision(
        pass_gate=passed,
        cal_open_authorized_for_next_controlled_run=passed,
        test_open_authorized=False,
        formal_g2="NOT_EVALUATED",
        reasons=reasons,
    )
