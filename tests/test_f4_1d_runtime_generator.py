from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

import simfleet_edg.demand.runtime_generator as module
from simfleet_edg.demand.runtime_context import RuntimeContext, ScenarioDayContext, runtime_row_id
from simfleet_edg.demand.runtime_generator import ProductionDGenGenerator, SelectedAdapters


@dataclass
class Record:
    candidate_id: str


class Participation:
    record = Record("PART_A")
    required_columns = ["household_size_class"]
    encoder = {
        "feature_columns": ["household_size_class"],
        "categories": {"household_size_class": ["1", "6_PLUS", "__MISSING_CONTEXT__", "__UNSEEN__"]},
        "feature_names": [],
    }

    def sample_one(self, frame: pd.DataFrame, *, seed: int) -> dict[str, Any]:
        return {"trip_day": True, "probability_trip_day": 1.0}


class TripCount:
    record = Record("COUNT_REF")
    required_columns: list[str] = []
    support = [1]

    def sample_one(self, frame: pd.DataFrame, *, seed: int) -> dict[str, Any]:
        return {"trip_count": 1}


class Chain:
    record = Record("CHAIN_A")
    model = {
        "levels": [
            {
                "dimensions": ["GLOBAL"],
                "cells": [
                    {
                        "key": [{"value": "GLOBAL"}],
                        "eligible_direct": True,
                        "probabilities": [1.0],
                    }
                ],
            }
        ]
    }

    def sample_initial_activity(self, *, seed: int) -> str:
        return "HOME"

    def sample_transition(self, frame: pd.DataFrame, *, seed: int) -> dict[str, Any]:
        return {"next_activity": "WORK"}


class Time:
    record = Record("TIME_B")
    encoder = {
        "categorical_columns": [],
        "numeric_columns": [],
        "categories": {},
        "feature_names": [],
    }


class Distance:
    record = Record("DIST_REF")

    def sample_one(self, frame: pd.DataFrame, *, seed: int) -> dict[str, Any]:
        return {"distance_prior_km": 2.5}


def _runtime(order: list[str]) -> RuntimeContext:
    scenario = ScenarioDayContext("RUNTIME_TEST", 3, 2)
    rows = []
    for person_id in order:
        rows.append(
            {
                "row_id": runtime_row_id(scenario.scenario_id, person_id),
                "source_household_id": f"HH_{person_id}",
                "source_person_id": person_id,
                "household_size_class": "1",
            }
        )
    return RuntimeContext(scenario, pd.DataFrame(rows))


def test_generator_is_order_independent_and_keeps_m1_identity(monkeypatch: Any) -> None:
    def fake_time(*args: Any, **kwargs: Any) -> tuple[dict[str, Any], dict[str, int]]:
        return (
            {
                "departure_clock_minute": 500,
                "arrival_absolute_minute": 530,
                "duration_from_clock_min": 30,
            },
            {},
        )

    monkeypatch.setattr(module, "_time_b_full_chain_sample", fake_time)
    adapters = SelectedAdapters(Participation(), TripCount(), Chain(), Time(), Distance())  # type: ignore[arg-type]
    generator = ProductionDGenGenerator(Path("."), adapters=adapters)

    first = generator.generate(_runtime(["P_2", "P_1"]))
    second = generator.generate(_runtime(["P_1", "P_2"]))
    pd.testing.assert_frame_equal(first.day_rows, second.day_rows)
    pd.testing.assert_frame_equal(first.trip_rows, second.trip_rows)
    assert set(first.day_rows["source_person_id"]) == {"P_1", "P_2"}
    assert first.support_audit["unhandled_runtime_categories"] == 0
    assert first.support_audit["chain_a_selected_level_counts"] == {"level_0": 2}
