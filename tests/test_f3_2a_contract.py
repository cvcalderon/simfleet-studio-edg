from __future__ import annotations

import csv
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
CFG = yaml.safe_load((ROOT / "configs/design/f3_2a_training_data_contract_v1.yaml").read_text(encoding="utf-8"))


def rows(name: str) -> list[dict[str, str]]:
    with (ROOT / "docs" / name).open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def test_parent_and_test_seal() -> None:
    assert CFG["required_parent_commit"] == "58bb4183a9557b8b8b069552813db9530cb848b0"
    assert CFG["test_partition"] == "SEALED"
    assert CFG["partitions"]["forbidden"] == ["TEST"]


def test_train_cal_physically_separate() -> None:
    assert CFG["partitions"]["allowed"] == ["TRAIN", "CALIBRATION"]
    assert CFG["partitions"]["physical_separation_required"] is True


def test_expected_train_anchors() -> None:
    r={(x["partition"],x["dataset"]):int(x["expected_rows"]) for x in rows("F3_2a_EXPECTED_ROW_COUNTS_v1.csv")}
    assert r[("TRAIN","participation")] == 2154
    assert r[("TRAIN","trip_count")] == 1791
    assert r[("TRAIN","chain_days")] == 1422
    assert r[("TRAIN","chain_transitions")] == 4872
    assert r[("TRAIN","time_trips")] == 6103
    assert r[("TRAIN","distance_raw")] == 5617


def test_no_test_counts() -> None:
    assert all(x["partition"] != "TEST" for x in rows("F3_2a_EXPECTED_ROW_COUNTS_v1.csv"))


def test_ids_weights_never_x() -> None:
    s=rows("F3_2a_DATASET_SCHEMA_v1.csv")
    x={r["column"] for r in s if r["allowed_in_X"] in {"YES","FIT_ONLY"}}
    assert not {"source_household_id","source_person_id","source_person_slot","source_trip_id"} & x
    assert not {c for c in {r["column"] for r in s} if "weight" in c.lower()} & x


def test_no_mode_or_km_routing_schema() -> None:
    cols={r["column"] for r in rows("F3_2a_DATASET_SCHEMA_v1.csv")}
    assert "km_routing" not in cols
    assert not any("mode" in c.lower() for c in cols)


def test_resource_semantics() -> None:
    r=rows("F3_2a_RESOURCE_CANONICALIZATION_v1.csv")
    assert len(r) == 9
    assert {x["semantic_group"] for x in r} == {"HOUSEHOLD_OWNERSHIP","PERSON_ACCESS"}
    assert any(x["canonical_column"] == "person_car_access" for x in r)


def test_r4_is_interface_only_and_missing_context_preserved() -> None:
    src=rows("F3_2a_SOURCE_MANIFEST_v1.csv")
    assert all(x["consumed_for_rows"] == "NO" for x in src if x["source_id"].startswith("r4_"))
    assert CFG["source_policy"]["no_silent_complete_case_shrinkage"] is True
    assert CFG["special_tokens"]["missing_context"] != CFG["special_tokens"]["source_unknown"]
