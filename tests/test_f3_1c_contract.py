from __future__ import annotations

import csv
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "configs/design/f3_1c_fit_cal_protocol_v1.yaml"


def contract() -> dict:
    return yaml.safe_load(CONTRACT.read_text(encoding="utf-8"))


def rows(name: str) -> list[dict[str, str]]:
    with (ROOT / "docs" / name).open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def test_parent_and_test_seal() -> None:
    c = contract()
    assert c["required_parent_commit"] == "ce99ff2f175fcc2df34cca3607754b4de9c4605d"
    assert c["test_partition"] == "SEALED"


def test_selection_is_lexicographic() -> None:
    c = contract()
    assert c["selection_rule"]["type"] == "LEXICOGRAPHIC_NO_COMPOSITE_SCORE"
    assert c["selection_rule"]["complexity_order"] == ["REFERENCE_BASELINE", "CORE_CANDIDATE_A", "CORE_CHALLENGER_B"]


def test_no_runtime_leak_policy() -> None:
    c = contract()
    assert c["feature_policy"]["weights_are_fit_weights_not_features"]
    assert c["feature_policy"]["technical_ids_are_keys_not_features"]
    assert not c["feature_policy"]["silent_rare_category_pooling"]


def test_count_tail_is_truncated_not_clipped() -> None:
    text = contract()["components"]["DG_TRIP_COUNT"]["tail_policy"]
    assert "truncated and renormalized" in text
    assert "never clipped" in text


def test_teacher_forcing_is_cal_only() -> None:
    chain = contract()["components"]["DG_ACTIVITY_CHAIN"]
    assert chain["teacher_forcing_for_component_cal_only"] is True
    assert chain["runtime_teacher_forcing"] is False


def test_timing_and_distance_boundaries() -> None:
    c = contract()["components"]
    assert "not executed route travel time" in c["DG_TIME_SCHEDULE"]["semantic_guardrail"]
    assert c["DG_DISTANCE_PRIOR"]["train_universe"] == "REF_TRAIN_DISTANCE_RAW"


def test_cal_replication_and_bootstrap() -> None:
    p = contract()["calibration_protocol"]
    assert p["stochastic_replicates_per_cal_person"] == 32
    assert p["bootstrap"]["unit"] == "HOUSEHOLD"
    assert p["bootstrap"]["replicates"] == 1000
    assert p["bootstrap"]["confidence_level"] == 0.95


def test_registries_are_complete() -> None:
    assert len(rows("F3_1c_FEATURE_SUBSETS_v1.csv")) == 15
    assert len(rows("F3_1c_OBJECTIVE_METRIC_REGISTRY_v1.csv")) == 15
    assert len(rows("F3_1c_HYPERPARAMETER_GRID_v1.csv")) >= 20
    assert len(rows("F3_1c_ACCEPTANCE_THRESHOLDS_v1.csv")) >= 10
    assert len(rows("F3_1c_DECISION_REGISTER_v1.csv")) == 17
