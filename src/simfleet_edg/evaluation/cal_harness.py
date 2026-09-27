"""F3.3c component execution harness.

The harness is data-source agnostic. Pre-CAL validation uses synthetic cases only.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

import pandas as pd

from simfleet_edg.evaluation.cal_evidence import EvidenceRow, canonical_payload
from simfleet_edg.evaluation.cal_protocol import (
    CAL_SCENARIO_ID,
    MASTER_SEED,
    runtime_draw_seed,
)
from simfleet_edg.evaluation.cal_state import EvaluationMode, one_row_frame, select_upstream_state

REPLICATES = 32
EVENT_BITS = 32
MAX_EVENT_INDEX = (1 << EVENT_BITS) - 1


class AdapterRecordLike(Protocol):
    component: str
    artifact_id: str
    candidate_id: str
    grid_id: str
    role: str


class AdapterLike(Protocol):
    record: AdapterRecordLike
    required_columns: list[str]


@dataclass(frozen=True)
class ComponentCase:
    source_household_id: str
    source_person_id: str
    event_index: int
    weight: float
    static_context: dict[str, Any]
    empirical_state: dict[str, Any] | None
    generated_state: dict[str, Any] | None
    observed: dict[str, Any]
    controls: dict[str, Any]

    @property
    def evaluation_person_id(self) -> str:
        return evaluation_person_id(self.source_household_id, self.source_person_id)


def evaluation_person_id(source_household_id: object, source_person_id: object) -> str:
    """Seed/provenance identity only; never a behavioral predictor."""
    return f"CAL|{source_household_id}|{source_person_id}"


def packed_draw_index(replicate_index: int, event_index: int) -> int:
    """Collision-free PRE-CAL encoding of replicate and within-person event slot."""
    if not 0 <= replicate_index < REPLICATES:
        raise ValueError(f"replicate_index must be in 0..{REPLICATES - 1}")
    if not 0 <= event_index <= MAX_EVENT_INDEX:
        raise ValueError("event_index must fit unsigned 32 bits")
    return (int(replicate_index) << EVENT_BITS) | int(event_index)


def _state_for(adapter: AdapterLike, case: ComponentCase, mode: EvaluationMode) -> dict[str, Any]:
    if adapter.record.component == "DG_PARTICIPATION":
        return dict(case.static_context)
    upstream = select_upstream_state(
        mode,
        empirical=case.empirical_state,
        generated=case.generated_state,
    )
    return {**case.static_context, **upstream}


def _execute_one(
    adapter: Any,
    frame: pd.DataFrame,
    *,
    case: ComponentCase,
    seed: int,
) -> dict[str, Any]:
    component = adapter.record.component
    if component in {"DG_PARTICIPATION", "DG_TRIP_COUNT", "DG_DISTANCE_PRIOR"}:
        return dict(adapter.sample_one(frame, seed=seed))
    if component == "DG_ACTIVITY_CHAIN":
        return dict(adapter.sample_transition(frame, seed=seed))
    if component == "DG_TIME_SCHEDULE":
        return dict(
            adapter.sample_one(
                frame,
                previous_arrival_absolute_minute=case.controls.get(
                    "previous_arrival_absolute_minute"
                ),
                trips_remaining_after_current=int(
                    case.controls.get("trips_remaining_after_current", 0)
                ),
                seed=seed,
            )
        )
    raise ValueError(f"Unsupported component {component}")


def execute_candidate(
    adapter: Any,
    cases: list[ComponentCase],
    *,
    mode: EvaluationMode | str,
    replicates: int = REPLICATES,
    master_seed: int = MASTER_SEED,
    scenario_id: str = CAL_SCENARIO_ID,
) -> list[EvidenceRow]:
    if replicates != REPLICATES:
        raise ValueError("F3.1c freezes CAL stochastic replicates to 32")
    parsed_mode = EvaluationMode(mode)
    rows: list[EvidenceRow] = []
    component = str(adapter.record.component)

    for replicate_id in range(replicates):
        for case in cases:
            draw_index = packed_draw_index(replicate_id, case.event_index)
            seed = runtime_draw_seed(
                master_seed,
                scenario_id,
                case.evaluation_person_id,
                component,
                draw_index,
            )
            state = _state_for(adapter, case, parsed_mode)
            frame = one_row_frame(state, list(adapter.required_columns))
            generated = _execute_one(adapter, frame, case=case, seed=seed)
            rows.append(
                EvidenceRow(
                    component=component,
                    artifact_id=str(adapter.record.artifact_id),
                    candidate_id=str(adapter.record.candidate_id),
                    grid_id=str(adapter.record.grid_id),
                    role=str(adapter.record.role),
                    evaluation_mode=parsed_mode.value,
                    replicate_id=replicate_id,
                    evaluation_person_id=case.evaluation_person_id,
                    source_household_id=str(case.source_household_id),
                    event_index=int(case.event_index),
                    draw_index=draw_index,
                    seed_u64=seed,
                    weight=float(case.weight),
                    observed_json=canonical_payload(case.observed),
                    generated_json=canonical_payload(generated),
                )
            )
    return rows
