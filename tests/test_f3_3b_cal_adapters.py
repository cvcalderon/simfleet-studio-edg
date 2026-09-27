from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest
import yaml

from simfleet_edg.evaluation.cal_adapter_common import AdapterDrawIdentity, load_registry
from simfleet_edg.evaluation.cal_adapter_factory import build_adapter, synthetic_smoke
from simfleet_edg.evaluation.cal_state import (
    EvaluationMode,
    departure_period,
    propagated_chain_state,
    propagated_distance_state,
    propagated_time_state,
    select_upstream_state,
    trip_position_class,
)

ROOT = Path.cwd()
CFG = yaml.safe_load((ROOT / "configs/f3/f3_3b_cal_adapters_v1.yaml").read_text())
REGISTRY = load_registry(ROOT / CFG["candidate_registry"]["path"])


def test_protocol_boundaries_are_still_closed():
    assert CFG["cal_partition"] == "UNOPENED"
    assert CFG["test_partition"] == "SEALED"
    assert CFG["candidate_selection"] == "NONE"
    assert CFG["cal_rows_read"] == 0


def test_registry_has_exact_31_artifacts():
    assert len(REGISTRY) == 31
    assert len({r.artifact_id for r in REGISTRY}) == 31


def test_component_counts():
    counts = pd.Series([r.component for r in REGISTRY]).value_counts().to_dict()
    assert counts == {
        "DG_PARTICIPATION": 8,
        "DG_TRIP_COUNT": 5,
        "DG_ACTIVITY_CHAIN": 6,
        "DG_TIME_SCHEDULE": 7,
        "DG_DISTANCE_PRIOR": 5,
    }


def test_isolated_uses_only_empirical_state():
    result = select_upstream_state(EvaluationMode.ISOLATED, empirical={"x": 1}, generated={"x": 2})
    assert result == {"x": 1}


def test_propagated_uses_only_generated_state():
    result = select_upstream_state(EvaluationMode.PROPAGATED, empirical={"x": 1}, generated={"x": 2})
    assert result == {"x": 2}


def test_missing_mode_specific_state_rejected():
    with pytest.raises(ValueError):
        select_upstream_state(EvaluationMode.ISOLATED, empirical=None, generated={"x": 1})
    with pytest.raises(ValueError):
        select_upstream_state(EvaluationMode.PROPAGATED, empirical={"x": 1}, generated=None)


@pytest.mark.parametrize(
    ("index", "count", "expected"),
    [(1, 1, "SINGLE"), (1, 3, "FIRST"), (2, 3, "MIDDLE"), (3, 3, "LAST")],
)
def test_trip_position(index, count, expected):
    assert trip_position_class(index, count) == expected


@pytest.mark.parametrize(
    ("minute", "expected"),
    [(0, "NIGHT"), (359, "NIGHT"), (360, "AM_PEAK"), (599, "AM_PEAK"),
     (600, "DAY"), (959, "DAY"), (960, "PM_PEAK"), (1199, "PM_PEAK"),
     (1200, "EVENING"), (1439, "EVENING")],
)
def test_departure_period(minute, expected):
    assert departure_period(minute) == expected


def test_propagated_chain_state_prefix_semantics():
    state = propagated_chain_state(
        {"primary_activity_status": "EMPLOYED_FULL_TIME", "source_weekday": 2},
        trip_count=3,
        prefix=["HOME"],
        remaining_trips=2,
    )
    assert state["prefix_second_last_activity"] == "__START__"
    assert state["prefix_last_activity"] == "HOME"
    assert state["source_trip_count_analogue"] == 3


def test_propagated_time_state_semantics():
    state = propagated_time_state(
        {"source_weekday": 2}, trip_count=2, trip_index=1,
        origin_activity="HOME", destination_activity="WORK",
        previous_departure_clock_minute=None, previous_arrival_absolute_minute=None,
    )
    assert state["trip_position_class"] == "FIRST"
    assert state["origin_activity_analogue"] == "HOME"


def test_propagated_distance_state_semantics():
    state = propagated_distance_state(
        {"source_weekday": 2}, trip_count=2, origin_activity="HOME",
        destination_activity="WORK", departure_clock_minute=480,
        arrival_absolute_minute=510, duration_from_clock_minute=30,
    )
    assert state["departure_period_analogue"] == "AM_PEAK"
    assert state["arrival_clock_minute_analogue"] == 510


def test_draw_identity_is_candidate_independent_within_component():
    identity = AdapterDrawIdentity(generated_person_id="P1", draw_index=7)
    a = identity.seed("DG_TRIP_COUNT")
    b = identity.seed("DG_TRIP_COUNT")
    c = identity.seed("DG_ACTIVITY_CHAIN")
    assert a == b
    assert a != c


@pytest.mark.parametrize("record", REGISTRY, ids=lambda r: r.artifact_id)
def test_all_frozen_artifacts_instantiate_and_smoke(record):
    adapter = build_adapter(ROOT, record)
    result = synthetic_smoke(adapter, seed=123456)
    assert isinstance(result, dict)
    assert result


def test_time_runtime_clarifications_exact():
    clar = CFG["time_runtime_clarifications"]
    assert clar["status"] == "FROZEN_PRE_CAL_IMPLEMENTATION_CLARIFICATIONS"
    assert clar["time_ref_rejection"]["max_rejection_attempts"] == 100
    assert clar["time_b_sampling"]["departure_duration_uniform_coupling"] == (
        "INDEPENDENT_UNIFORMS_FROM_SAME_EVENT_SEED_STREAM"
    )
    assert clar["time_b_sampling"]["minute_integerization"] == "ROUND_HALF_UP"


def test_no_cal_data_files_are_named_in_adapter_config():
    payload = json.dumps(CFG).lower()
    assert "calibration/" not in payload
    assert "test/" not in payload
