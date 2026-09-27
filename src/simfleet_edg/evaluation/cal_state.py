"""ISOLATED/PROPAGATED state projections frozen before CAL inspection."""

from __future__ import annotations

import math
from collections.abc import Mapping
from enum import StrEnum
from typing import Any

import pandas as pd


class EvaluationMode(StrEnum):
    ISOLATED = "ISOLATED"
    PROPAGATED = "PROPAGATED"


def select_upstream_state(
    mode: EvaluationMode | str,
    *,
    empirical: Mapping[str, Any] | None,
    generated: Mapping[str, Any] | None,
) -> dict[str, Any]:
    parsed = EvaluationMode(mode)
    if parsed is EvaluationMode.ISOLATED:
        if empirical is None:
            raise ValueError("ISOLATED evaluation requires empirical upstream state")
        return dict(empirical)
    if generated is None:
        raise ValueError("PROPAGATED evaluation requires generated upstream state")
    return dict(generated)


def one_row_frame(state: Mapping[str, Any], required_columns: list[str]) -> pd.DataFrame:
    missing = [column for column in required_columns if column not in state]
    if missing:
        raise KeyError(f"Missing adapter-state fields: {missing}")
    return pd.DataFrame([{column: state[column] for column in required_columns}])


def trip_position_class(trip_index: int, trip_count: int) -> str:
    if trip_count < 1 or not 1 <= trip_index <= trip_count:
        raise ValueError("trip_index must be inside 1..trip_count")
    if trip_count == 1:
        return "SINGLE"
    if trip_index == 1:
        return "FIRST"
    if trip_index == trip_count:
        return "LAST"
    return "MIDDLE"


def departure_period(clock_minute: int | float) -> str:
    value = float(clock_minute)
    if not math.isfinite(value) or value < 0 or value >= 1440:
        raise ValueError("departure clock must be in [0,1440)")
    minute = int(value)
    if minute < 360:
        return "NIGHT"
    if minute < 600:
        return "AM_PEAK"
    if minute < 960:
        return "DAY"
    if minute < 1200:
        return "PM_PEAK"
    return "EVENING"


def propagated_chain_state(
    static_context: Mapping[str, Any],
    *,
    trip_count: int,
    prefix: list[str],
    remaining_trips: int,
) -> dict[str, Any]:
    if not prefix:
        raise ValueError("chain prefix must contain the current origin activity")
    return {
        **dict(static_context),
        "source_trip_count_analogue": int(trip_count),
        "prefix_second_last_activity": "__START__" if len(prefix) == 1 else str(prefix[-2]),
        "prefix_last_activity": str(prefix[-1]),
        "remaining_trips": int(remaining_trips),
    }


def propagated_time_state(
    static_context: Mapping[str, Any],
    *,
    trip_count: int,
    trip_index: int,
    origin_activity: str,
    destination_activity: str,
    previous_departure_clock_minute: int | None,
    previous_arrival_absolute_minute: int | None,
) -> dict[str, Any]:
    return {
        **dict(static_context),
        "source_trip_count_analogue": int(trip_count),
        "origin_activity_analogue": str(origin_activity),
        "destination_activity_analogue": str(destination_activity),
        "trip_position_class": trip_position_class(trip_index, trip_count),
        "previous_departure_clock_minute": previous_departure_clock_minute,
        "previous_arrival_absolute_minute": previous_arrival_absolute_minute,
    }


def propagated_distance_state(
    static_context: Mapping[str, Any],
    *,
    trip_count: int,
    origin_activity: str,
    destination_activity: str,
    departure_clock_minute: int,
    arrival_absolute_minute: int,
    duration_from_clock_minute: int,
) -> dict[str, Any]:
    return {
        **dict(static_context),
        "source_trip_count_analogue": int(trip_count),
        "origin_activity_analogue": str(origin_activity),
        "destination_activity_analogue": str(destination_activity),
        "departure_clock_minute_analogue": int(departure_clock_minute),
        "departure_period_analogue": departure_period(departure_clock_minute),
        "arrival_clock_minute_analogue": int(arrival_absolute_minute) % 1440,
        "duration_from_clock_min_analogue": int(duration_from_clock_minute),
    }
