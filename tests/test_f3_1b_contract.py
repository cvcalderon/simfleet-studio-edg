from __future__ import annotations

import csv
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
CFG = ROOT / "configs/design/f3_1b_model_family_contract_v1.yaml"


def load_cfg() -> dict:
    return yaml.safe_load(CFG.read_text(encoding="utf-8"))


def test_component_set_is_frozen() -> None:
    assert set(load_cfg()["components"]) == {
        "DG_PARTICIPATION", "DG_TRIP_COUNT", "DG_ACTIVITY_CHAIN", "DG_TIME_SCHEDULE", "DG_DISTANCE_PRIOR"
    }


def test_test_partition_is_sealed() -> None:
    cfg = load_cfg()
    assert cfg["test_partition"] == "SEALED"
    assert "zero model-family" in cfg["calibration_role"]["TEST"]


def test_low_support_rule_matches_f2_2() -> None:
    cfg = load_cfg()
    assert cfg["support_policy"]["min_source_rows_for_direct_conditional_cell"] == 30
    assert cfg["support_policy"]["silent_pooling"] is False


def test_count_candidate_preserves_participation_hurdle() -> None:
    family = load_cfg()["components"]["DG_TRIP_COUNT"]["candidate_A"]["family"]
    assert "K_MINUS_1" in family


def test_time_semantics_do_not_claim_executed_route_time() -> None:
    guardrail = load_cfg()["components"]["DG_TIME_SCHEDULE"]["semantic_guardrail"]
    assert "not executed route travel time" in guardrail


def test_distance_primary_uses_raw_wegkm() -> None:
    family = load_cfg()["components"]["DG_DISTANCE_PRIOR"]["candidate_A"]["family"]
    assert "RAW_WEGKM" in family


def test_llm_schedule_is_not_core_candidate() -> None:
    path = ROOT / "docs/F3_1b_CANDIDATE_MATRIX_v1.csv"
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    llm = [row for row in rows if row["candidate_id"] == "CHAIN_LLM"]
    assert len(llm) == 1
    assert llm[0]["role"] == "OUT_OF_CORE_EXPERIMENTAL"


def test_rng_namespaces_are_component_specific() -> None:
    cfg = load_cfg()
    assert len(cfg["rng_contract"]["namespaces"]) == 5
    assert "canonical lexical key" in cfg["rng_contract"]["candidate_order"]
