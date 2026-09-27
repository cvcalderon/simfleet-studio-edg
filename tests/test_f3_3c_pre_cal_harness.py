from __future__ import annotations

import json
from dataclasses import dataclass

import numpy as np
import pandas as pd
import pytest

from simfleet_edg.evaluation.cal_access_guard import PartitionAccess
from simfleet_edg.evaluation.cal_bootstrap_eval import (
    mean_metric_over_replicates,
    paired_household_bootstrap_difference,
)
from simfleet_edg.evaluation.cal_evidence import assert_candidate_pairing, evidence_frame
from simfleet_edg.evaluation.cal_harness import (
    REPLICATES,
    ComponentCase,
    evaluation_person_id,
    execute_candidate,
    packed_draw_index,
)
from simfleet_edg.evaluation.cal_protocol import bootstrap_seed
from simfleet_edg.evaluation.cal_state import EvaluationMode


@dataclass(frozen=True)
class _Record:
    component: str
    artifact_id: str
    candidate_id: str
    grid_id: str
    role: str


class _ParticipationStub:
    required_columns = ["x"]

    def __init__(self, artifact_id: str, offset: float):
        self.record = _Record(
            "DG_PARTICIPATION", artifact_id, "PART_A", artifact_id, "CORE_CANDIDATE_A"
        )
        self.offset = offset

    def sample_one(self, frame: pd.DataFrame, *, seed: int) -> dict[str, object]:
        rng = np.random.default_rng(seed)
        p = min(max(float(frame.iloc[0]["x"]) + self.offset, 0.01), 0.99)
        return {"probability_trip_day": p, "trip_day": bool(rng.random() < p)}


class _CountStub:
    required_columns = ["k_context"]

    def __init__(self, artifact_id: str):
        self.record = _Record(
            "DG_TRIP_COUNT", artifact_id, "COUNT_A", artifact_id, "CORE_CANDIDATE_A"
        )

    def sample_one(self, frame: pd.DataFrame, *, seed: int) -> dict[str, object]:
        rng = np.random.default_rng(seed)
        return {"trip_count": int(frame.iloc[0]["k_context"]) + int(rng.integers(0, 2))}


class _ChainStub:
    required_columns = ["prefix_last_activity"]

    def __init__(self):
        self.record = _Record(
            "DG_ACTIVITY_CHAIN", "CHAIN_A::X", "CHAIN_A", "X", "CORE_CANDIDATE_A"
        )

    def sample_transition(self, frame: pd.DataFrame, *, seed: int) -> dict[str, object]:
        choices = ["HOME", "WORK"]
        value = choices[int(np.random.default_rng(seed).integers(0, 2))]
        return {"destination_activity": value}


class _TimeStub:
    required_columns = ["minute"]

    def __init__(self):
        self.record = _Record(
            "DG_TIME_SCHEDULE", "TIME_A::X", "TIME_A", "X", "CORE_CANDIDATE_A"
        )

    def sample_one(
        self,
        frame: pd.DataFrame,
        *,
        previous_arrival_absolute_minute: int | None,
        trips_remaining_after_current: int,
        seed: int,
    ) -> dict[str, object]:
        del previous_arrival_absolute_minute, trips_remaining_after_current
        return {
            "departure_clock_minute": int(frame.iloc[0]["minute"]),
            "arrival_absolute_minute": int(frame.iloc[0]["minute"])
            + int(np.random.default_rng(seed).integers(1, 10)),
        }


class _DistanceStub:
    required_columns = ["d"]

    def __init__(self):
        self.record = _Record(
            "DG_DISTANCE_PRIOR", "DIST_A::X", "DIST_A", "X", "CORE_CANDIDATE_A"
        )

    def sample_one(self, frame: pd.DataFrame, *, seed: int) -> dict[str, object]:
        return {
            "distance_prior_km": float(frame.iloc[0]["d"])
            + float(np.random.default_rng(seed).random())
        }


def _case(event: int = 0) -> ComponentCase:
    return ComponentCase(
        source_household_id="10",
        source_person_id="20",
        event_index=event,
        weight=2.0,
        static_context={"x": 0.6},
        empirical_state={"k_context": 3, "prefix_last_activity": "HOME", "minute": 500, "d": 2.0},
        generated_state={"k_context": 4, "prefix_last_activity": "WORK", "minute": 600, "d": 3.0},
        observed={"target": 1},
        controls={"previous_arrival_absolute_minute": None, "trips_remaining_after_current": 0},
    )


def test_person_identity_is_exact():
    assert evaluation_person_id(10, 20) == "CAL|10|20"


@pytest.mark.parametrize("rep,event", [(0, 0), (1, 0), (31, 7)])
def test_packed_draw_index(rep: int, event: int):
    value = packed_draw_index(rep, event)
    assert value == (rep << 32) | event


def test_packed_draw_index_rejects_outside_protocol():
    with pytest.raises(ValueError):
        packed_draw_index(32, 0)
    with pytest.raises(ValueError):
        packed_draw_index(0, 1 << 32)


def test_exact_32_replicates_and_unique_keys():
    rows = execute_candidate(
        _ParticipationStub("A", 0.0), [_case()], mode=EvaluationMode.ISOLATED
    )
    assert len(rows) == REPLICATES == 32
    frame = evidence_frame(rows)
    assert frame["replicate_id"].tolist() == list(range(32))


def test_candidate_independent_crn():
    left = evidence_frame(
        execute_candidate(_ParticipationStub("A", 0.0), [_case()], mode="ISOLATED")
    )
    right = evidence_frame(
        execute_candidate(_ParticipationStub("B", 0.1), [_case()], mode="ISOLATED")
    )
    assert_candidate_pairing(left, right)
    assert left["seed_u64"].tolist() == right["seed_u64"].tolist()


def test_pairing_rejects_seed_mismatch():
    left = evidence_frame(
        execute_candidate(_ParticipationStub("A", 0.0), [_case()], mode="ISOLATED")
    )
    right = left.copy()
    right.loc[0, "seed_u64"] = int(right.loc[0, "seed_u64"]) + 1
    with pytest.raises(ValueError):
        assert_candidate_pairing(left, right)


def test_isolated_and_propagated_choose_different_upstream_state():
    isolated = evidence_frame(
        execute_candidate(_CountStub("A"), [_case()], mode=EvaluationMode.ISOLATED)
    )
    propagated = evidence_frame(
        execute_candidate(_CountStub("A"), [_case()], mode=EvaluationMode.PROPAGATED)
    )
    i0 = json.loads(isolated.iloc[0]["generated_json"])["trip_count"]
    p0 = json.loads(propagated.iloc[0]["generated_json"])["trip_count"]
    assert p0 - i0 == 1


@pytest.mark.parametrize(
    "adapter,event",
    [
        (_ChainStub(), 1),
        (_TimeStub(), 2),
        (_DistanceStub(), 3),
    ],
)
def test_event_components_execute_32_replicates(adapter, event):
    rows = execute_candidate(adapter, [_case(event)], mode="ISOLATED")
    frame = evidence_frame(rows)
    assert len(frame) == 32
    assert set(frame["event_index"]) == {event}


def test_access_guard_blocks_cal_and_test():
    guard = PartitionAccess()
    guard.assert_pre_cal()
    with pytest.raises(PermissionError):
        guard.require_cal()
    with pytest.raises(PermissionError):
        guard.require_test()


def test_access_guard_rejects_precal_authorization():
    with pytest.raises(ValueError):
        PartitionAccess(cal_authorized=True).assert_pre_cal()
    with pytest.raises(ValueError):
        PartitionAccess(test_authorized=True).assert_pre_cal()


def _scalar_metric(frame: pd.DataFrame, multiplier: np.ndarray) -> float:
    generated = np.array(
        [json.loads(value)["probability_trip_day"] for value in frame["generated_json"]],
        dtype=float,
    )
    weights = frame["weight"].to_numpy(dtype=float) * multiplier
    return float(np.average(generated, weights=weights))


def test_mean_metric_is_arithmetic_mean_of_32():
    evidence = evidence_frame(
        execute_candidate(_ParticipationStub("A", 0.0), [_case()], mode="ISOLATED")
    )
    value = mean_metric_over_replicates(
        evidence, np.ones(len(evidence), dtype=int), _scalar_metric
    )
    assert value == pytest.approx(0.6)


def test_bootstrap_is_1000_household_paired_recomputations():
    cases = [
        _case(),
        ComponentCase(
            source_household_id="11",
            source_person_id="21",
            event_index=0,
            weight=1.0,
            static_context={"x": 0.3},
            empirical_state={"k_context": 2},
            generated_state={"k_context": 2},
            observed={"target": 0},
            controls={},
        ),
    ]
    incumbent = evidence_frame(
        execute_candidate(_ParticipationStub("I", 0.0), cases, mode="ISOLATED")
    )
    challenger = evidence_frame(
        execute_candidate(_ParticipationStub("C", -0.05), cases, mode="ISOLATED")
    )
    seed = bootstrap_seed(20260926, "DG_PARTICIPATION", "I", "C")
    diffs, interval = paired_household_bootstrap_difference(
        incumbent,
        challenger,
        _scalar_metric,
        bootstrap_replicates=1000,
        seed=seed,
    )
    assert len(diffs) == 1000
    assert interval.replicates == 1000
    assert interval.confidence_level == pytest.approx(0.95)
    assert np.all(np.isfinite(diffs))


def test_bootstrap_rejects_non_1000():
    evidence = evidence_frame(
        execute_candidate(_ParticipationStub("A", 0.0), [_case()], mode="ISOLATED")
    )
    with pytest.raises(ValueError):
        paired_household_bootstrap_difference(
            evidence,
            evidence,
            _scalar_metric,
            bootstrap_replicates=999,
            seed=1,
        )
