from __future__ import annotations

import csv
from pathlib import Path

import yaml  # type: ignore[import-untyped]

ROOT = Path(__file__).resolve().parents[1]


def test_f4_1d_config_matches_frozen_pipeline_and_smoke() -> None:
    cfg = yaml.safe_load(
        (ROOT / "configs/f4/f4_1d_runtime_dgen_binding_preopen_v1.yaml").read_text(
            encoding="utf-8"
        )
    )
    assert cfg["phase_id"] == "F4.1d"
    assert cfg["required_parent_commit"] == "eebccc7a43eb7c1ef2661da3f357c0e5b01e72ef"
    assert cfg["master_seed"] == 20261007
    assert [row["artifact_id"] for row in cfg["selected_pipeline"]] == [
        "DG_PARTICIPATION::PART_A::PA1",
        "DG_TRIP_COUNT::COUNT_REF::REFERENCE",
        "DG_ACTIVITY_CHAIN::CHAIN_A::CHA2",
        "TIME_B_TB2",
        "DIST_REF_REFERENCE",
    ]
    assert cfg["smoke"] == {
        "population": 512,
        "selection": "FIRST_CANONICAL_PERSON_ID_LEXICAL",
        "scenario_id": "F4_1D_BINDING_SMOKE_V1",
        "scenario_weekday": 3,
        "scenario_season": 2,
        "replicate_index": 0,
        "downstream_authorized": False,
    }
    assert cfg["execution_boundary"]["full_100k_dgen_realization"] == "FORBIDDEN"
    assert cfg["execution_boundary"]["terminal_git_push"] == "FORBIDDEN"


def test_f4_1d_model_binding_csv_exact_selected_set() -> None:
    with (ROOT / "docs/F4_1D_MODEL_BINDINGS_v1.csv").open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 5
    assert {row["runtime_state"] for row in rows} == {"FROZEN_SELECTED_ONLY"}
    assert {row["artifact_id"] for row in rows} == {
        "DG_PARTICIPATION::PART_A::PA1",
        "DG_TRIP_COUNT::COUNT_REF::REFERENCE",
        "DG_ACTIVITY_CHAIN::CHAIN_A::CHA2",
        "TIME_B_TB2",
        "DIST_REF_REFERENCE",
    }


def test_f4_1d_overlay_declares_exactly_17_paths() -> None:
    paths = [
        line.strip()
        for line in (ROOT / "docs/F4_1D_OVERLAY_FILELIST_v1.txt").read_text(
            encoding="utf-8"
        ).splitlines()
        if line.strip()
    ]
    assert len(paths) == 17
    assert len(set(paths)) == 17
