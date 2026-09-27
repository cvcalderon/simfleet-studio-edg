"""Factory and synthetic artifact-smoke helpers for F3.3b."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from simfleet_edg.evaluation.activity_chain_adapter import ActivityChainAdapter
from simfleet_edg.evaluation.cal_adapter_common import ArtifactRecord, canonical_category
from simfleet_edg.evaluation.distance_prior_adapter import DistancePriorAdapter
from simfleet_edg.evaluation.participation_adapter import ParticipationAdapter
from simfleet_edg.evaluation.time_schedule_adapter import TimeScheduleAdapter
from simfleet_edg.evaluation.trip_count_adapter import TripCountAdapter


def build_adapter(repo_root: Path, record: ArtifactRecord) -> Any:
    mapping = {
        "DG_PARTICIPATION": ParticipationAdapter,
        "DG_TRIP_COUNT": TripCountAdapter,
        "DG_ACTIVITY_CHAIN": ActivityChainAdapter,
        "DG_TIME_SCHEDULE": TimeScheduleAdapter,
        "DG_DISTANCE_PRIOR": DistancePriorAdapter,
    }
    try:
        cls = mapping[record.component]
    except KeyError as exc:
        raise ValueError(f"Unknown component {record.component}") from exc
    return cls(repo_root, record)


def _first_nonreserved(values: list[Any]) -> Any:
    for value in values:
        if str(value) not in {"__MISSING_CONTEXT__", "__UNSEEN__", "__START__"}:
            return value
    return values[0]


def synthetic_state_from_full_encoder(encoder: dict[str, Any]) -> dict[str, Any]:
    state: dict[str, Any] = {}
    for column, values in encoder.get("categories", {}).items():
        state[column] = _first_nonreserved(list(values))
    for column in encoder.get("numeric_columns", []):
        state[column] = 1.0
    return state


def synthetic_state_from_reference_encoder(encoder: dict[str, Any]) -> dict[str, Any]:
    state: dict[str, Any] = {}
    for column in encoder.get("feature_columns", encoder.get("categorical_columns", [])):
        state[column] = encoder.get("reference_categories", {}).get(
            column, _first_nonreserved(list(encoder["categories"][column]))
        )
    for column in encoder.get("numeric_columns", []):
        scaler = encoder.get("numeric_scalers", {}).get(column, {})
        state[column] = float(scaler.get("mean", 1.0))
    return state


def _eligible_state_from_backoff(model: dict[str, Any]) -> dict[str, Any]:
    all_dimensions: list[str] = []
    for level in model["levels"]:
        for dimension in level["dimensions"]:
            if dimension != "GLOBAL" and dimension not in all_dimensions:
                all_dimensions.append(dimension)
    base = {dimension: "__MISSING_CONTEXT__" for dimension in all_dimensions}
    for level in model["levels"]:
        dims = list(level["dimensions"])
        if dims == ["GLOBAL"]:
            continue
        for cell in level["cells"]:
            if not bool(cell["eligible_direct"]):
                continue
            key = cell["key"]
            state = dict(base)
            if isinstance(key, dict):
                state.update({k: v for k, v in key.items()})
            elif key and isinstance(key[0], dict):
                state.update({item["dimension"]: item["value"] for item in key})
            else:
                state.update(dict(zip(dims, [canonical_category(v) for v in key], strict=True)))
            return state
    return base


def synthetic_smoke(adapter: Any, *, seed: int = 12345) -> dict[str, Any]:
    record = adapter.record
    if record.component == "DG_PARTICIPATION":
        state = synthetic_state_from_full_encoder(adapter.encoder)
        return adapter.sample_one(pd.DataFrame([state]), seed=seed)

    if record.component == "DG_TRIP_COUNT":
        if record.candidate_id == "COUNT_A":
            state = synthetic_state_from_reference_encoder(adapter.encoder)
        elif record.candidate_id == "COUNT_B":
            state = _eligible_state_from_backoff(adapter.model)
        else:
            state = {}
        return adapter.sample_one(pd.DataFrame([state]), seed=seed)

    if record.component == "DG_ACTIVITY_CHAIN":
        if record.candidate_id == "CHAIN_B":
            state = synthetic_state_from_reference_encoder(adapter.encoder)
            state["source_trip_count_analogue"] = 2
            state["remaining_trips"] = 1
            state["prefix_second_last_activity"] = "__START__"
            state["prefix_last_activity"] = "HOME"
        elif record.candidate_id == "CHAIN_A":
            state = _eligible_state_from_backoff(adapter.model)
        else:
            state = {"prefix_last_activity": "HOME"}
        return adapter.sample_transition(pd.DataFrame([state]), seed=seed)

    if record.component == "DG_TIME_SCHEDULE":
        if record.candidate_id == "TIME_B":
            state = synthetic_state_from_full_encoder(adapter.encoder)
            state["source_trip_count_analogue"] = 1
            state["previous_departure_clock_minute"] = np.nan
            state["previous_arrival_absolute_minute"] = np.nan
        elif record.candidate_id == "TIME_A":
            state = _eligible_state_from_backoff(adapter.model)
        else:
            state = {}
        return adapter.sample_one(
            pd.DataFrame([state]),
            previous_arrival_absolute_minute=None,
            trips_remaining_after_current=0,
            seed=seed,
        )

    if record.component == "DG_DISTANCE_PRIOR":
        if record.candidate_id == "DIST_B":
            state = synthetic_state_from_full_encoder(adapter.encoder)
            state.update({
                "source_trip_count_analogue": 1,
                "departure_clock_minute_analogue": 720,
                "arrival_clock_minute_analogue": 750,
                "duration_from_clock_min_analogue": 30,
            })
        elif record.candidate_id == "DIST_A":
            state = _eligible_state_from_backoff(adapter.model)
        else:
            state = {}
        return adapter.sample_one(pd.DataFrame([state]), seed=seed)

    raise ValueError(record.component)
