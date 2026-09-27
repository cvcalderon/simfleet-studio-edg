"""Lexicographic no-composite-score selection primitives."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class GridScore:
    artifact_id: str
    candidate_id: str
    grid_id: str
    role: str
    primary_metric: float
    hard_pass: bool
    guardrails_pass: bool


@dataclass(frozen=True)
class PromotionDecision:
    incumbent_artifact_id: str
    challenger_artifact_id: str
    point_improvement: float
    practical_margin: float
    bootstrap_ci_lower: float
    bootstrap_ci_upper: float
    promoted: bool
    reasons: tuple[str, ...]


def choose_within_family(scores: Iterable[GridScore]) -> GridScore | None:
    eligible = [s for s in scores if s.hard_pass and s.guardrails_pass]
    if not eligible:
        return None
    if not all(np.isfinite(s.primary_metric) for s in eligible):
        raise ValueError("primary metrics must be finite")
    return sorted(eligible, key=lambda s: (s.primary_metric, s.grid_id))[0]


def promotion_decision(
    incumbent: GridScore,
    challenger: GridScore,
    *,
    practical_margin: float,
    bootstrap_ci_lower: float,
    bootstrap_ci_upper: float,
) -> PromotionDecision:
    if not incumbent.hard_pass or not incumbent.guardrails_pass:
        raise ValueError("incumbent must be valid")
    improvement = float(incumbent.primary_metric - challenger.primary_metric)
    reasons: list[str] = []
    if not challenger.hard_pass:
        reasons.append("HARD_INVARIANT_FAILURE")
    if not challenger.guardrails_pass:
        reasons.append("GUARDRAIL_FAILURE")
    if improvement < practical_margin:
        reasons.append("PRACTICAL_MARGIN_NOT_MET")
    if not bootstrap_ci_lower > 0:
        reasons.append("BOOTSTRAP_CI_NOT_STRICTLY_ABOVE_ZERO")
    promoted = len(reasons) == 0
    return PromotionDecision(
        incumbent_artifact_id=incumbent.artifact_id,
        challenger_artifact_id=challenger.artifact_id,
        point_improvement=improvement,
        practical_margin=float(practical_margin),
        bootstrap_ci_lower=float(bootstrap_ci_lower),
        bootstrap_ci_upper=float(bootstrap_ci_upper),
        promoted=promoted,
        reasons=tuple(reasons),
    )
