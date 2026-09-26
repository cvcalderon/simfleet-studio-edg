from __future__ import annotations

from pathlib import Path

import pandas as pd
import yaml

from simfleet_edg.demand.training_data import (
    DATASETS,
    PARTITIONS,
    _car_access,
    _membership,
    _stock_class,
    _yes_no,
    departure_period,
    deterministic_row_id,
    load_schema_columns,
)

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "configs/f3/f3_2b_materialize_training_data.yaml"
SCHEMA = ROOT / "docs/F3_2a_DATASET_SCHEMA_v1.csv"
COUNTS = ROOT / "docs/F3_2a_EXPECTED_ROW_COUNTS_v1.csv"
SOURCES = ROOT / "docs/F3_2a_SOURCE_MANIFEST_v1.csv"


def test_f32b_001_partitions_are_train_cal_only() -> None:
    config = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    assert tuple(config["partitions"]) == PARTITIONS
    assert config["forbidden_partitions"] == ["TEST"]


def test_f32b_002_dataset_family_matches_frozen_contract() -> None:
    columns = load_schema_columns(SCHEMA)
    assert tuple(columns) == DATASETS
    assert len(columns) == 8


def test_f32b_003_resource_canonicalization_preserves_semantics() -> None:
    assert _stock_class(3, 3) == "3_PLUS"
    assert _stock_class(10, 10) == "10_PLUS"
    assert _stock_class(99, 3) == "UNKNOWN"
    assert _membership(1) == "ONE_PROVIDER"
    assert _membership(3) == "NONE"
    assert _car_access(2) == "OCCASIONAL"
    assert _yes_no(2) == "NO"


def test_f32b_004_departure_period_boundaries_are_frozen() -> None:
    assert departure_period(0) == "NIGHT"
    assert departure_period(359) == "NIGHT"
    assert departure_period(360) == "AM_PEAK"
    assert departure_period(599) == "AM_PEAK"
    assert departure_period(600) == "DAY"
    assert departure_period(959) == "DAY"
    assert departure_period(960) == "PM_PEAK"
    assert departure_period(1199) == "PM_PEAK"
    assert departure_period(1200) == "EVENING"
    assert departure_period(None) == "__MISSING_CONTEXT__"


def test_f32b_005_row_id_is_deterministic_and_partition_specific() -> None:
    first = deterministic_row_id("TRAIN", 10, 11, "person_day_context")
    assert first == deterministic_row_id("TRAIN", 10, 11, "person_day_context")
    assert first != deterministic_row_id("CALIBRATION", 10, 11, "person_day_context")
    assert len(first) == 64


def test_f32b_006_expected_counts_are_exact_contract_rows() -> None:
    frame = pd.read_csv(COUNTS)
    assert len(frame) == 16
    expected = frame.set_index(["partition", "dataset"])["expected_rows"].to_dict()
    assert expected[("TRAIN", "person_day_context")] == 2200
    assert expected[("TRAIN", "chain_transitions")] == 4872
    assert expected[("CALIBRATION", "distance_raw")] == 1147


def test_f32b_007_source_manifest_keeps_r4_as_interface_only() -> None:
    frame = pd.read_csv(SOURCES)
    assert len(frame) == 13
    r4 = frame[frame["source_id"].str.startswith("r4_")]
    assert len(r4) == 3
    assert r4["consumed_for_rows"].eq("NO").all()


def test_f32b_008_output_schema_excludes_mode_route_execution() -> None:
    schema = pd.read_csv(SCHEMA)
    joined = " ".join(schema["column"].astype(str)).lower()
    assert "km_routing" not in joined
    assert "chosen_mode" not in joined
    assert "observed_mode" not in joined
    assert "mode_family" not in joined
    assert "execution" not in joined
