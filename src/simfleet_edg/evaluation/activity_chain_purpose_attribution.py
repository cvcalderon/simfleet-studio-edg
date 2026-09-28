"""TRAIN-only purpose attribution primitive for generated activity-chain transitions."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import Any

import pandas as pd

DIRECT_PURPOSE = {
    "HOME": "RETURN_HOME",
    "WORK": "WORK_COMMUTE",
    "BUSINESS": "BUSINESS",
    "EDUCATION": "EDUCATION",
    "SHOPPING": "SHOPPING",
    "PRIVATE_ERRAND": "PRIVATE_ERRAND",
    "ESCORT": "ESCORT",
    "LEISURE": "LEISURE",
    "OTHER": "OTHER",
}

BACKOFF_LEVELS = (
    ("L1", ("prefix_last_activity", "target_destination_activity", "remaining_trips", "source_trip_count_analogue")),
    ("L2", ("prefix_last_activity", "target_destination_activity", "remaining_trips")),
    ("L3", ("prefix_last_activity", "target_destination_activity")),
    ("L4", ("target_destination_activity",)),
)

REQUIRED_COLUMNS = {
    "prefix_second_last_activity",
    "prefix_last_activity",
    "target_destination_activity",
    "remaining_trips",
    "source_trip_count_analogue",
    "canonical_trip_purpose",
    "fit_weight_W_GEW",
}


def _json_scalar(value: Any) -> Any:
    if pd.isna(value):
        return None
    if hasattr(value, "item"):
        return value.item()
    return value


def _json_key(values: Sequence[Any]) -> list[Any]:
    return [_json_scalar(value) for value in values]


def _weighted_probability(frame: pd.DataFrame) -> tuple[float, float, float]:
    weight = float(frame["fit_weight_W_GEW"].sum())
    if not math.isfinite(weight) or weight <= 0.0:
        raise ValueError("Positive finite weight required")
    rp_weight = float(
        frame.loc[frame["is_return_previous"].eq(1), "fit_weight_W_GEW"].sum()
    )
    return weight, rp_weight, rp_weight / weight


def validate_purpose_semantics(frame: pd.DataFrame) -> dict[str, int]:
    missing = REQUIRED_COLUMNS - set(frame.columns)
    if missing:
        raise ValueError(f"Missing columns: {sorted(missing)}")
    mapped = frame["target_destination_activity"].map(DIRECT_PURPOSE)
    if mapped.isna().any():
        raise ValueError("Unmapped destination activity")
    rp = frame["canonical_trip_purpose"].eq("RETURN_PREVIOUS")
    rp_bad = rp & (
        frame["target_destination_activity"]
        != frame["prefix_second_last_activity"]
    )
    direct_bad = (~rp) & (frame["canonical_trip_purpose"] != mapped)
    return {
        "return_previous_violations": int(rp_bad.sum()),
        "direct_mapping_violations": int(direct_bad.sum()),
    }


def fit_purpose_attribution(
    frame: pd.DataFrame,
    *,
    source_n_min: int = 30,
) -> dict[str, Any]:
    semantic = validate_purpose_semantics(frame)
    if any(semantic.values()):
        raise ValueError("Purpose semantic invariants failed")

    work = frame.copy()
    work["is_return_previous"] = (
        work["canonical_trip_purpose"].eq("RETURN_PREVIOUS").astype(int)
    )
    eligible = work[
        work["target_destination_activity"]
        == work["prefix_second_last_activity"]
    ].copy()
    if eligible.empty:
        raise ValueError("No return-eligible TRAIN rows")

    gw, grw, gp = _weighted_probability(eligible)
    levels = []
    for level_name, dimensions in BACKOFF_LEVELS:
        cells = []
        for key, group in eligible.groupby(
            list(dimensions), dropna=False, sort=True
        ):
            if not isinstance(key, tuple):
                key = (key,)
            weight, rp_weight, probability = _weighted_probability(group)
            source_n = int(len(group))
            cells.append(
                {
                    "key": _json_key(key),
                    "source_n": source_n,
                    "weight": weight,
                    "return_previous_weight": rp_weight,
                    "p_return_previous": probability,
                    "eligible_direct": source_n >= source_n_min,
                }
            )
        levels.append(
            {
                "level": level_name,
                "dimensions": list(dimensions),
                "cells": cells,
            }
        )

    return {
        "primitive_id": "CHAIN_PURPOSE_ATTRIBUTION_V1",
        "fit_partition": "TRAIN",
        "source_n_min": source_n_min,
        "smoothing": "NONE",
        "probability_estimator": "WEIGHTED_BERNOULLI_MLE",
        "direct_mapping": DIRECT_PURPOSE,
        "semantic_validation": semantic,
        "train_rows": int(len(work)),
        "return_previous_rows": int(work["is_return_previous"].sum()),
        "return_eligible_rows": int(len(eligible)),
        "global_return_eligible": {
            "source_n": int(len(eligible)),
            "weight": gw,
            "return_previous_weight": grw,
            "p_return_previous": gp,
        },
        "levels": levels,
    }


def _lookup(level: Mapping[str, Any], state: Mapping[str, Any]) -> dict[str, Any] | None:
    dims = list(level["dimensions"])
    requested = _json_key([state.get(dim) for dim in dims])
    for cell in level["cells"]:
        if list(cell["key"]) == requested:
            return dict(cell)
    return None


def resolve_return_previous_probability(
    artifact: Mapping[str, Any],
    state: Mapping[str, Any],
) -> tuple[str, float, int]:
    destination = str(state["target_destination_activity"])
    previous_origin = str(state.get("prefix_second_last_activity"))
    if destination != previous_origin:
        return "NOT_RETURN_ELIGIBLE", 0.0, 0
    for level in artifact["levels"]:
        cell = _lookup(level, state)
        if cell is not None and bool(cell["eligible_direct"]):
            return (
                str(level["level"]),
                float(cell["p_return_previous"]),
                int(cell["source_n"]),
            )
    global_cell = artifact["global_return_eligible"]
    return (
        "L5_GLOBAL",
        float(global_cell["p_return_previous"]),
        int(global_cell["source_n"]),
    )


def attribute_generated_purpose(
    artifact: Mapping[str, Any],
    state: Mapping[str, Any],
    *,
    u: float,
) -> str:
    if not 0.0 <= u < 1.0:
        raise ValueError("u must be in [0,1)")
    destination = str(state["target_destination_activity"])
    if destination not in DIRECT_PURPOSE:
        raise ValueError(f"Unsupported destination: {destination}")
    direct = DIRECT_PURPOSE[destination]
    level, probability, _ = resolve_return_previous_probability(artifact, state)
    if level == "NOT_RETURN_ELIGIBLE":
        return direct
    return "RETURN_PREVIOUS" if u < probability else direct


def backoff_selection_audit(
    frame: pd.DataFrame,
    artifact: Mapping[str, Any],
) -> dict[str, Any]:
    eligible = frame[
        frame["target_destination_activity"]
        == frame["prefix_second_last_activity"]
    ].copy()
    rows = []
    for idx, row in eligible.iterrows():
        level, probability, source_n = resolve_return_previous_probability(
            artifact, row.to_dict()
        )
        rows.append(
            {
                "row_index": int(idx),
                "level": level,
                "source_n": source_n,
                "p_return_previous": probability,
                "weight": float(row["fit_weight_W_GEW"]),
            }
        )
    selected = pd.DataFrame(rows)
    total_weight = float(selected["weight"].sum())
    levels = ["L1", "L2", "L3", "L4", "L5_GLOBAL"]
    return {
        "selected_level_rows": {
            level: int(selected["level"].eq(level).sum()) for level in levels
        },
        "selected_level_weight_shares": {
            level: float(
                selected.loc[selected["level"].eq(level), "weight"].sum()
                / total_weight
            )
            for level in levels
        },
        "selected_rows_with_p_zero": int(
            selected["p_return_previous"].eq(0.0).sum()
        ),
        "selected_weight_share_with_p_zero": float(
            selected.loc[
                selected["p_return_previous"].eq(0.0), "weight"
            ].sum()
            / total_weight
        ),
        "selected_rows_with_p_one": int(
            selected["p_return_previous"].eq(1.0).sum()
        ),
    }
