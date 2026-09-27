"""F3.3 PRE-CAL protocol identities and deterministic seed utilities."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

COMPONENT_ORDER = (
    "DG_PARTICIPATION",
    "DG_TRIP_COUNT",
    "DG_ACTIVITY_CHAIN",
    "DG_TIME_SCHEDULE",
    "DG_DISTANCE_PRIOR",
)

COMPLEXITY_RANK = {
    "REFERENCE_BASELINE": 0,
    "CORE_CANDIDATE_A": 1,
    "CORE_CHALLENGER_B": 2,
}

MASTER_SEED = 20260926
CAL_SCENARIO_ID = "CAL_EVAL_V1"


def _sha256_u64(text: str) -> int:
    return int.from_bytes(hashlib.sha256(text.encode("utf-8")).digest()[:8], "big")


def runtime_draw_seed(
    master_seed: int,
    scenario_id: str,
    generated_person_id: str | int,
    component_namespace: str,
    draw_index: int,
) -> int:
    """Frozen F3.1c runtime draw stream as uint64."""
    payload = (
        f"{master_seed}|{scenario_id}|{generated_person_id}|"
        f"{component_namespace}|{draw_index}"
    )
    return _sha256_u64(payload)


def bootstrap_seed(
    master_seed: int,
    component: str,
    incumbent_artifact_id: str,
    challenger_artifact_id: str,
) -> int:
    """PRE-CAL clarification: deterministic paired-bootstrap namespace."""
    payload = (
        "F3_3_BOOTSTRAP_V1|"
        f"{master_seed}|{component}|{incumbent_artifact_id}|{challenger_artifact_id}"
    )
    return _sha256_u64(payload)


def part_b_household_fold(
    source_household_id: str | int,
    master_seed: int = MASTER_SEED,
    folds: int = 5,
) -> int:
    if folds != 5:
        raise ValueError("F3.1c freezes PART_B cross-fit folds to 5")
    payload = f"F3_3_PART_B_CAL_FOLD_V1|{master_seed}|{source_household_id}"
    return _sha256_u64(payload) % folds


@dataclass(frozen=True)
class EvaluationIdentity:
    component: str
    candidate_id: str
    grid_id: str
    artifact_id: str
    role: str

    @property
    def complexity_rank(self) -> int:
        return COMPLEXITY_RANK[self.role]
