"""Selected-vs-reference CAL joint gate primitive."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class JointGateInput:
    structural_invariant_violations: int
    temporal_invariant_violations: int
    nofuture_violations: int
    selected_component_dominated: bool
    selected_pipeline_material_degradation: bool
    selected_artifact_manifests_frozen: bool
    post_cal_design_change: bool


@dataclass(frozen=True)
class JointGateDecision:
    pass_gate: bool
    test_open_authorized: bool
    formal_g2: str
    reasons: tuple[str, ...]


def joint_cal_gate(value: JointGateInput) -> JointGateDecision:
    reasons: list[str] = []
    if value.structural_invariant_violations != 0:
        reasons.append("STRUCTURAL_INVARIANT_VIOLATIONS")
    if value.temporal_invariant_violations != 0:
        reasons.append("TEMPORAL_INVARIANT_VIOLATIONS")
    if value.nofuture_violations != 0:
        reasons.append("NOFUTURE_VIOLATIONS")
    if value.selected_component_dominated:
        reasons.append("SELECTED_COMPONENT_DOMINATED")
    if value.selected_pipeline_material_degradation:
        reasons.append("MATERIAL_DEGRADATION_VS_ALL_REFERENCE")
    if not value.selected_artifact_manifests_frozen:
        reasons.append("SELECTED_ARTIFACT_IDENTITIES_NOT_FROZEN")
    if value.post_cal_design_change:
        reasons.append("POST_CAL_DESIGN_CHANGE")
    ok = len(reasons) == 0
    return JointGateDecision(
        pass_gate=ok,
        test_open_authorized=ok,
        formal_g2="NOT_EVALUATED",
        reasons=tuple(reasons),
    )
