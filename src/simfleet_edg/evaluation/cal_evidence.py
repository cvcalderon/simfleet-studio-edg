"""Standardized F3.3c CAL-evaluation evidence records.

This module contains no CAL/TEST I/O.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from typing import Any

import pandas as pd


def canonical_payload(value: dict[str, Any]) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


@dataclass(frozen=True)
class EvidenceRow:
    component: str
    artifact_id: str
    candidate_id: str
    grid_id: str
    role: str
    evaluation_mode: str
    replicate_id: int
    evaluation_person_id: str
    source_household_id: str
    event_index: int
    draw_index: int
    seed_u64: int
    weight: float
    observed_json: str
    generated_json: str

    def as_record(self) -> dict[str, Any]:
        return asdict(self)


EVIDENCE_KEY = (
    "component",
    "artifact_id",
    "evaluation_mode",
    "replicate_id",
    "evaluation_person_id",
    "event_index",
)


def evidence_frame(rows: list[EvidenceRow]) -> pd.DataFrame:
    frame = pd.DataFrame([row.as_record() for row in rows])
    if frame.empty:
        raise ValueError("evidence rows must not be empty")
    if frame.duplicated(list(EVIDENCE_KEY)).any():
        raise ValueError("duplicate evidence key")
    if (frame["replicate_id"] < 0).any():
        raise ValueError("replicate_id must be non-negative")
    if (frame["event_index"] < 0).any():
        raise ValueError("event_index must be non-negative")
    if (frame["weight"] <= 0).any():
        raise ValueError("evidence weights must be positive")
    return frame


def assert_candidate_pairing(left: pd.DataFrame, right: pd.DataFrame) -> None:
    """Require candidate-independent person/event/replicate seeds."""
    key = [
        "component",
        "evaluation_mode",
        "replicate_id",
        "evaluation_person_id",
        "source_household_id",
        "event_index",
        "draw_index",
    ]
    left_rows = left[key + ["seed_u64"]].sort_values(key).reset_index(drop=True)
    right_rows = right[key + ["seed_u64"]].sort_values(key).reset_index(drop=True)
    if not left_rows[key].equals(right_rows[key]):
        raise ValueError("paired candidates do not cover the same evidence keys")
    if not left_rows["seed_u64"].equals(right_rows["seed_u64"]):
        raise ValueError("paired candidates do not use common random numbers")
