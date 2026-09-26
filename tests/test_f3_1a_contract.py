from __future__ import annotations

import csv
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
CFG = yaml.safe_load((ROOT / "configs/design/f3_1a_dgen_contract_v1.yaml").read_text())


def rows(name: str):
    with (ROOT / "docs" / name).open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def test_component_order_exact():
    assert CFG["component_order"] == [
        "DG_PARTICIPATION", "DG_TRIP_COUNT", "DG_ACTIVITY_CHAIN", "DG_TIME_SCHEDULE", "DG_DISTANCE_PRIOR"
    ]


def test_runtime_boundary_excludes_realised_source_outcomes():
    assert "REALISED_SOURCE_OUTCOME_AS_RUNTIME_FEATURE" in CFG["runtime_boundary"]["forbidden"]


def test_feature_registry_classes_are_closed_enum():
    valid = {"ALLOWED_RUNTIME", "FIT_ONLY_EVIDENCE", "FORBIDDEN_FUTURE_INFORMATION", "IDENTIFIER_PROVENANCE_ONLY"}
    assert all(r["information_class"] in valid for r in rows("F3_1a_INFORMATION_FEATURE_REGISTRY_v1.csv"))


def test_weights_and_source_ids_are_not_allowed_runtime():
    reg = rows("F3_1a_INFORMATION_FEATURE_REGISTRY_v1.csv")
    by_name = {r["field_or_group"]: r for r in reg}
    assert by_name["P_GEW"]["information_class"] == "FIT_ONLY_EVIDENCE"
    assert by_name["W_GEW"]["information_class"] == "FIT_ONLY_EVIDENCE"
    assert by_name["source_hp_id_h_id_p_id"]["information_class"] == "IDENTIFIER_PROVENANCE_ONLY"


def test_downstream_fields_forbidden_in_trip_intent():
    forbidden = set(CFG["output_contract"]["TripIntent"]["forbidden_fields"])
    assert {"generated_destination_coordinate", "chosen_mode", "km_routing", "execution_outcome"} <= forbidden


def test_test_partition_is_sealed_and_g2_not_evaluated():
    assert CFG["test_partition"] == "SEALED"
    assert CFG["formal_g2"] == "NOT_EVALUATED"


def test_all_five_components_have_target_mapping():
    mapped = {r["component"] for r in rows("F3_1a_COMPONENT_TARGET_MAPPING_v1.csv")}
    assert set(CFG["component_order"]) <= mapped


def test_model_family_is_deferred_to_f3_1b():
    assert CFG["model_family_selection"] == "UNSELECTED_F3_1B"
    dec = {r["decision_id"]: r for r in rows("F3_1a_DECISION_REGISTER_v1.csv")}
    assert dec["F3A-MODEL-001"]["state"] == "DEFERRED_TO_F3_1B"
