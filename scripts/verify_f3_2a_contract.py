from __future__ import annotations

import csv
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
CFG = ROOT / "configs/design/f3_2a_training_data_contract_v1.yaml"
DOC = ROOT / "docs"


def load_csv(name: str) -> list[dict[str, str]]:
    with (DOC / name).open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def verify() -> dict[str, object]:
    cfg = yaml.safe_load(CFG.read_text(encoding="utf-8"))
    src = load_csv("F3_2a_SOURCE_MANIFEST_v1.csv")
    counts = load_csv("F3_2a_EXPECTED_ROW_COUNTS_v1.csv")
    schema = load_csv("F3_2a_DATASET_SCHEMA_v1.csv")
    resource = load_csv("F3_2a_RESOURCE_CANONICALIZATION_v1.csv")
    decisions = load_csv("F3_2a_DECISION_REGISTER_v1.csv")

    schema_cols = {r["column"] for r in schema}
    x_cols = {r["column"] for r in schema if r["allowed_in_X"] in {"YES", "FIT_ONLY"}}
    source_ids = {r["source_id"] for r in src}
    ds_counts = {(r["partition"], r["dataset"]): int(r["expected_rows"]) for r in counts}
    checks = {
        "contract_present": CFG.exists(),
        "parent_f3_1c_exact": cfg["required_parent_commit"] == "58bb4183a9557b8b8b069552813db9530cb848b0",
        "test_sealed": cfg["test_partition"] == "SEALED",
        "formal_g2_not_evaluated": cfg["formal_g2"] == "NOT_EVALUATED",
        "allowed_partitions_exact": cfg["partitions"]["allowed"] == ["TRAIN", "CALIBRATION"],
        "test_forbidden_partition": cfg["partitions"]["forbidden"] == ["TEST"],
        "physical_split_required": cfg["partitions"]["physical_separation_required"] is True,
        "cal_never_fit": "NEVER_FIT" in cfg["partitions"]["cal_role"],
        "source_manifest_13": len(src) == 13,
        "raw_source_hashes_present": {"raw_households", "raw_persons"}.issubset(source_ids),
        "f0_task_sources_present": {"f0_3b_personday_coverage", "f0_3c_person_sequence", "f0_3c_trip_transition", "f0_3d_trip_time", "f0_3e_trip_spatial"}.issubset(source_ids),
        "r4_not_fit_source": all(r["consumed_for_rows"] == "NO" for r in src if r["source_id"].startswith("r4_")),
        "ids_not_features": not {"source_household_id", "source_person_id", "source_person_slot", "source_trip_id"}.intersection(x_cols),
        "weights_not_features": not {c for c in schema_cols if "weight" in c.lower()}.intersection(x_cols),
        "km_routing_absent": "km_routing" not in schema_cols,
        "mode_absent": not any("mode" in c.lower() for c in schema_cols),
        "resource_rows_9": len(resource) == 9,
        "ownership_access_separate": {r["semantic_group"] for r in resource} == {"HOUSEHOLD_OWNERSHIP", "PERSON_ACCESS"},
        "calendar_weekday_1_7": cfg["calendar_mapping"]["domain"] == [1,2,3,4,5,6,7],
        "calendar_season_1_4": cfg["calendar_mapping"]["season_domain"] == [1,2,3,4],
        "holiday_deferred": cfg["calendar_mapping"]["holiday_role"].startswith("DEFERRED"),
        "train_context_2200": ds_counts[("TRAIN", "person_day_context")] == 2200,
        "train_part_2154": ds_counts[("TRAIN", "participation")] == 2154,
        "train_count_1791": ds_counts[("TRAIN", "trip_count")] == 1791,
        "train_chain_days_1422": ds_counts[("TRAIN", "chain_days")] == 1422,
        "train_chain_transitions_4872": ds_counts[("TRAIN", "chain_transitions")] == 4872,
        "train_time_6103": ds_counts[("TRAIN", "time_trips")] == 6103,
        "train_distance_5617": ds_counts[("TRAIN", "distance_raw")] == 5617,
        "train_distance_expanded_6145": ds_counts[("TRAIN", "distance_expanded_sensitivity")] == 6145,
        "cal_counts_present_without_test": len([k for k in ds_counts if k[0] == "CALIBRATION"]) == 8 and not any(k[0] == "TEST" for k in ds_counts),
        "missing_context_token_distinct": cfg["special_tokens"]["missing_context"] != cfg["special_tokens"]["source_unknown"],
        "train_vocab_only": cfg["category_vocabulary"]["fit_partition"] == "TRAIN_ONLY",
        "no_complete_case_shrinkage": cfg["source_policy"]["no_silent_complete_case_shrinkage"] is True,
        "distance_missing_backoff": cfg["row_retention"]["distance_missing_time_action"].endswith("BACKOFF"),
        "csv_byte_audit": cfg["serialization"]["data_format"] == "CSV" and cfg["serialization"]["byte_hash"] == "SHA256",
        "decisions_20": len(decisions) == 20,
        "implementation_deferred": any(r["state"] == "DEFERRED" and r["topic"] == "Implementation" for r in decisions),
    }
    return {
        "status": "PASS" if all(checks.values()) else "FAIL",
        "checks": checks,
        "counts": {
            "sources": len(src),
            "expected_count_rows": len(counts),
            "schema_rows": len(schema),
            "resource_rows": len(resource),
            "decisions": len(decisions),
        },
    }


if __name__ == "__main__":
    import json

    print(json.dumps(verify(), indent=2))
