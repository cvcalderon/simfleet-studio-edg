import json
from pathlib import Path

import yaml

from simfleet_edg.repro.f3_4g2a_joint_synthetic import (
    FORBIDDEN_STATIC,
    JointAdapters,
    build_synthetic_static_context,
    make_synthetic_cohort,
    safe_category,
)

ROOT = Path(__file__).resolve().parents[1]
CFG = ROOT / "configs/f3/f3_4g2a_joint_synthetic_preopen_v1.yaml"
REG = ROOT / "configs/f3/f3_4g1_joint_pipeline_registry_v1.json"


class FakePart:
    encoder = {
        "feature_columns": ["sex", "activity"],
        "categories": {
            "sex": ["__MISSING_CONTEXT__", "F"],
            "activity": ["WORK", "__UNSEEN__"],
        },
    }


class FakeRecord:
    candidate_id = "CHAIN_A"


class FakeChain:
    record = FakeRecord()
    model = {
        "levels": [
            {
                "dimensions": ["sex", "prefix_last_activity"],
                "cells": [
                    {
                        "eligible_direct": True,
                        "key": [
                            {"value": "F"},
                            {"value": "HOME"},
                        ],
                    }
                ],
            }
        ]
    }


class FakeTimeRecord:
    candidate_id = "TIME_B"


class FakeTime:
    record = FakeTimeRecord()
    encoder = {
        "categorical_columns": ["sex", "origin_activity_analogue"],
        "numeric_columns": ["age_numeric", "previous_arrival_absolute_minute"],
        "categories": {
            "sex": ["F", "__UNSEEN__"],
            "origin_activity_analogue": ["HOME", "__UNSEEN__"],
        },
    }


class Dummy:
    pass


def load_cfg() -> dict:
    return yaml.safe_load(CFG.read_text(encoding="utf-8"))


def test_parent_and_zero_access_boundaries() -> None:
    cfg = load_cfg()
    assert cfg["required_parent_commit"] == (
        "19e903ffbc4cb914d2b70d637bae2e82d1200e30"
    )
    assert cfg["access_boundaries"]["cal_rows_read"] == 0
    assert cfg["access_boundaries"]["test_rows_read"] == 0
    assert cfg["access_boundaries"]["joint_real_cal_open_authorized"] is False


def test_two_exact_pipeline_definitions() -> None:
    registry = json.loads(REG.read_text(encoding="utf-8"))
    assert len(registry["selected_pipeline"]) == 5
    assert len(registry["all_reference_pipeline"]) == 5
    assert registry["selected_pipeline"][0]["artifact_id"] == (
        "DG_PARTICIPATION::PART_A::PA1"
    )
    assert registry["all_reference_pipeline"][0]["artifact_id"] == (
        "DG_PARTICIPATION::PART_REF::REFERENCE"
    )


def test_synthetic_protocol_uses_32_crn_replicates() -> None:
    protocol = load_cfg()["synthetic_protocol"]
    assert protocol["stochastic_replicates"] == 32
    assert protocol["master_seed"] == 20260926
    assert protocol["scenario_id"] == "CAL_EVAL_V1"
    assert protocol["common_random_numbers"] is True
    assert protocol["same_seed_schedule_across_pipelines"] is True


def test_synthetic_metrics_are_nondecision() -> None:
    smoke = load_cfg()["synthetic_smoke"]
    assert smoke["metric_smoke_decision_authorized"] is False
    assert smoke["selection_authorized"] is False


def test_safe_category_avoids_reserved_when_possible() -> None:
    assert safe_category(["__UNSEEN__", "A"]) == "A"


def test_static_context_builder_uses_only_runtime_static_fields() -> None:
    adapters = JointAdapters(
        participation=FakePart(),  # type: ignore[arg-type]
        trip_count=Dummy(),  # type: ignore[arg-type]
        chain=FakeChain(),  # type: ignore[arg-type]
        time=FakeTime(),  # type: ignore[arg-type]
        distance=Dummy(),  # type: ignore[arg-type]
    )
    static = build_synthetic_static_context(adapters)
    assert static["sex"] == "F"
    assert static["activity"] == "WORK"
    assert static["age_numeric"] == 0.0
    assert "origin_activity_analogue" not in static
    assert "previous_arrival_absolute_minute" not in static
    assert not (FORBIDDEN_STATIC & set(static))


def test_make_synthetic_cohort_has_unique_person_ids() -> None:
    frame = make_synthetic_cohort({"sex": "F"}, 8)
    assert len(frame) == 8
    assert frame["row_id"].is_unique
    assert frame["source_person_id"].is_unique


def test_expected_synthetic_day_rows_are_512() -> None:
    cfg = load_cfg()
    assert cfg["synthetic_smoke"]["expected_day_rows"] == 2 * 32 * 8


def test_joint_gate_and_test_remain_closed() -> None:
    boundary = load_cfg()["access_boundaries"]
    assert boundary["joint_gate_evaluated"] is False
    assert boundary["joint_real_cal_open_authorized"] is False
    assert boundary["test_open_authorized"] is False
    assert boundary["formal_g2"] == "NOT_EVALUATED"


def test_no_calibration_path_is_declared_as_runtime_input() -> None:
    cfg = load_cfg()
    serialized = json.dumps(cfg, sort_keys=True)
    assert "CALIBRATION/" not in serialized
    assert cfg["access_boundaries"]["cal_files_read"] == []
