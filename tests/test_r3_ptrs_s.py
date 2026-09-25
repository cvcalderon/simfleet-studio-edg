from __future__ import annotations

import hashlib
import json
from pathlib import Path

from simfleet_edg.common.population_materializer import (
    age_infr_class,
    dataframe_csv_bytes,
    deterministic_zone_assignment,
    historical_population_manifest,
    largest_remainder_zone_quotas,
    materialize_population,
    snapshot_sha256,
    weighted_exact_person_draws,
    write_dataframe_csv,
    zone_allocation_audit,
)

ROOT = Path(__file__).resolve().parents[1]
REFERENCE = ROOT / "configs" / "reproduction" / "reference"


def test_r3_age_infr_boundaries_match_frozen_labels() -> None:
    assert age_infr_class(2) == "01_LT3"
    assert age_infr_class(3) == "02_3_5"
    assert age_infr_class(18) == "05_16_18"
    assert age_infr_class(19) == "06_19_24"
    assert age_infr_class(74) == "10_67_74"
    assert age_infr_class(75) == "11_75_PLUS"
    assert age_infr_class(85) == "11_75_PLUS"


def test_r3_snapshot_hash_matches_frozen_f13a_witness() -> None:
    primary = [
        "2eb514ed76136263d64fa8a7e237a2fcbbd1deb360dc8d2cb9cfe2f1cc38c601",
        "da3c22b2dd30f8e1a190d8c82a6df32254a91d33241cca6ff170a8d0d7f464c5",
        "981a0c697bb61d8903480f6ef573037daa661e4e82f1c467989a3c91e04aedb4",
    ]
    assert snapshot_sha256(primary) == (
        "f37ffeda502929bdda4c16f0c30d297fd6c2743b4c1e50e987471c6e714f9d01"
    )


def test_r3_zone_quota_reproduces_frozen_f13a_hash(tmp_path: Path) -> None:
    target = REFERENCE / "f1_2a_plr_universe_residual_audit_v1.csv"
    quota = largest_remainder_zone_quotas(target, 5663)
    audit = zone_allocation_audit(quota)
    out = tmp_path / "zone.csv"
    write_dataframe_csv(audit, out)

    assert int(audit["source_private_households_total"].notna().sum()) == 541
    assert int((audit["source_private_households_total"].fillna(0) > 0).sum()) == 540
    assert float(audit["source_private_households_total"].sum()) == 1960317.0
    assert int(audit["generated_households"].sum()) == 5663
    assert hashlib.sha256(out.read_bytes()).hexdigest() == (
        "457e87b0943895e22dfe31eb17da340de3a2b3a191aacc41998d7abe8e52879a"
    )
    assert len(deterministic_zone_assignment(quota, 20260923)) == 5663


def test_r3_historical_manifest_serialization_is_exact() -> None:
    manifest = historical_population_manifest(
        target_persons=10000,
        actual_persons=10000,
        actual_households=5663,
        actual_resource_relations=64263,
        generation_algorithm="WEIGHTED_WHOLE_HOUSEHOLD_EXACT_PERSON_TARGET_V1",
        generation_seed=20260922,
        zone_algorithm="PLR_PRIVATE_HH_TOTAL_LARGEST_REMAINDER_RANDOM_ASSIGN_V1",
        zone_seed=20260923,
        donor_pool_size=1219,
        linked_persons=8987,
        roster_only_persons=1013,
        snapshot_hash=(
            "f37ffeda502929bdda4c16f0c30d297fd6c2743b4c1e50e987471c6e714f9d01"
        ),
    )
    payload = (json.dumps(manifest, indent=2, ensure_ascii=False) + "\n").encode()
    assert hashlib.sha256(payload).hexdigest() == (
        "e1d2617095277bd2364116874ff7acf569c62083bef1f7a98eaedda3e1c08007"
    )


def test_r3_whole_household_sampler_is_deterministic_and_exact() -> None:
    donors = [
        {"H_ID": "1", "H_GR": "1", "H_GEW": "1"},
        {"H_ID": "2", "H_GR": "2", "H_GEW": "2"},
        {"H_ID": "3", "H_GR": "3", "H_GEW": "3"},
        {"H_ID": "4", "H_GR": "4", "H_GEW": "4"},
        {"H_ID": "5", "H_GR": "5", "H_GEW": "5"},
    ]
    a = weighted_exact_person_draws(donors, target_persons=37, seed=20260922)
    b = weighted_exact_person_draws(donors, target_persons=37, seed=20260922)
    assert [row["H_ID"] for row in a] == [row["H_ID"] for row in b]
    assert sum(int(row["H_GR"]) for row in a) == 37
    assert all(1 <= int(row["H_GR"]) <= 5 for row in a)


def test_r3_materializer_preserves_optional_source_ids_as_integer_or_blank() -> None:
    donor = {
        "H_ID": "100",
        "H_ART": "2",
        "H_GR": "2",
        "H_GEW": "2.5",
        "H_HOCH": "12.5",
        "H_ANZAUTO": "1",
        "H_ANZMOTMOP": "0",
        "H_ANZPED": "0",
        "H_ANZRAD": "2",
        "H_CS": "3",
        "HP_SEX_1": "1",
        "HP_ALTER_1": "40",
        "HP_TAET_1": "1",
        "HP_SEX_2": "2",
        "HP_ALTER_2": "12",
        "HP_TAET_2": "8",
    }
    person_lookup = {
        ("100", 1): {
            "H_ID": "100",
            "P_ID": "101",
            "P_GEW": "3.25",
            "P_HOCH": "17.5",
            "P_FS_PKW": "1",
            "P_VAUTO": "1",
            "P_VRAD": "2",
            "P_VPED": "2",
            "P_CS": "3",
        }
    }
    activity = {
        1: ("EMPLOYED_FULL_TIME", "EMPLOYED", "FULL_TIME"),
        8: ("SCHOOL", "NOT_EMPLOYED", "NOT_EMPLOYED"),
    }
    households, persons, resources = materialize_population(
        [donor],
        ["02400623"],
        person_lookup,
        activity,
        "P_TRS_EXP_V1",
        "S",
        20260922,
    )
    assert len(households) == 1
    assert len(persons) == 2
    assert len(resources) == 9
    person_csv = dataframe_csv_bytes(persons).decode()
    resource_csv = dataframe_csv_bytes(resources).decode()
    assert ",101,LINKED_PERSONEN," in person_csv
    assert ",101.0,LINKED_PERSONEN," not in person_csv
    assert "ROSTER_ONLY_NO_PERSONEN" in person_csv
    assert ",101,REL_S_" in resource_csv
    assert ",101.0,REL_S_" not in resource_csv
