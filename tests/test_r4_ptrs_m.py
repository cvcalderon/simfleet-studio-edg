from __future__ import annotations

import hashlib
import json
from pathlib import Path

from simfleet_edg.common.population_materializer import (
    deterministic_zone_assignment,
    largest_remainder_zone_quotas,
    materialize_population,
    snapshot_sha256,
    write_dataframe_csv,
    zone_allocation_audit,
)
from simfleet_edg.repro.r4_ptrs_m import historical_m_manifest

ROOT = Path(__file__).resolve().parents[1]
REFERENCE = ROOT / "configs" / "reproduction" / "reference"


def test_r4_snapshot_hash_matches_frozen_f13b_witness() -> None:
    primary = [
        "a7aed5fdfa1e55ec94781733b3144d5ffab8d9051b2663e5eb6672939948ee42",
        "e75c5c2ba417ddbd87bc074796f6052675cc325c1cec1f671fb8faf288edf70c",
        "c4f6ecdf7556a66e0faa5eba7704d7cc54c99fbf9387082c2a4c599f7f390842",
    ]
    assert snapshot_sha256(primary) == (
        "a3a9be46286d150e1032d1872ca0e47775407ee14835980f0d5a71be92c57f7d"
    )


def test_r4_zone_quota_reproduces_frozen_f13b_hash(tmp_path: Path) -> None:
    target = REFERENCE / "f1_2a_plr_universe_residual_audit_v1.csv"
    quota = largest_remainder_zone_quotas(target, 56365)
    audit = zone_allocation_audit(quota)
    out = tmp_path / "zone.csv"
    write_dataframe_csv(audit, out)

    assert int(audit["source_private_households_total"].notna().sum()) == 541
    assert int((audit["source_private_households_total"].fillna(0) > 0).sum()) == 540
    assert float(audit["source_private_households_total"].sum()) == 1960317.0
    assert int(audit["generated_households"].sum()) == 56365
    assert hashlib.sha256(out.read_bytes()).hexdigest() == (
        "c970671e96c0d93460371817175153f510a84ae6a528d9ce93ddb51e13754627"
    )
    assert len(deterministic_zone_assignment(quota, 20260923)) == 56365


def test_r4_historical_manifest_serialization_is_exact() -> None:
    import yaml

    config = yaml.safe_load(
        (ROOT / "configs" / "reproduction" / "r4_ptrs_m.yaml").read_text(
            encoding="utf-8"
        )
    )
    manifest = historical_m_manifest(
        actual_persons=100000,
        actual_households=56365,
        actual_resource_relations=639661,
        linked_persons=89459,
        roster_only_persons=10541,
        snapshot_hash=(
            "a3a9be46286d150e1032d1872ca0e47775407ee14835980f0d5a71be92c57f7d"
        ),
        validation_total=23,
        validation_pass=23,
        validation_fail=0,
        config=config,
    )
    payload = (json.dumps(manifest, indent=2, ensure_ascii=False) + "\n").encode()
    assert hashlib.sha256(payload).hexdigest() == (
        "5cbaf6248d70a6cd29df59556516cd1fa8a7630630f6e24ad1f9a1d523c66d7f"
    )


def test_r4_materializer_uses_historical_m_identifier_widths() -> None:
    donor = {
        "H_ID": "100",
        "H_ART": "1",
        "H_GR": "1",
        "H_GEW": "1.0",
        "H_HOCH": "2.0",
        "H_ANZAUTO": "0",
        "H_ANZMOTMOP": "0",
        "H_ANZPED": "0",
        "H_ANZRAD": "1",
        "H_CS": "3",
        "HP_SEX_1": "1",
        "HP_ALTER_1": "40",
        "HP_TAET_1": "1",
    }
    person_lookup = {
        ("100", 1): {
            "H_ID": "100",
            "P_ID": "1",
            "HP_ID": "1001",
            "P_GEW": "1.0",
            "P_HOCH": "2.0",
            "P_FS_PKW": "1",
            "P_VAUTO": "1",
            "P_VRAD": "1",
            "P_VPED": "2",
            "P_CS": "3",
        }
    }
    activity = {1: ("EMPLOYED_FULL_TIME", "EMPLOYED", "FULL_TIME")}
    households, persons, resources = materialize_population(
        [donor], ["1100101"], person_lookup, activity, "P_TRS_EXP_V1", "M", 20260922
    )
    assert households.iloc[0]["household_id"] == "HH_P_TRS_EXP_V1_M_0000001"
    assert persons.iloc[0]["person_id"] == "P_P_TRS_EXP_V1_M_0000001_01"
    assert resources.iloc[0]["relation_id"] == "REL_M_00000001"


def test_r4_materializer_keeps_s_identifier_widths_unchanged() -> None:
    donor = {
        "H_ID": "100",
        "H_ART": "1",
        "H_GR": "1",
        "H_GEW": "1.0",
        "H_HOCH": "2.0",
        "H_ANZAUTO": "0",
        "H_ANZMOTMOP": "0",
        "H_ANZPED": "0",
        "H_ANZRAD": "1",
        "H_CS": "3",
        "HP_SEX_1": "1",
        "HP_ALTER_1": "40",
        "HP_TAET_1": "1",
    }
    activity = {1: ("EMPLOYED_FULL_TIME", "EMPLOYED", "FULL_TIME")}
    households, persons, resources = materialize_population(
        [donor], ["1100101"], {}, activity, "P_TRS_EXP_V1", "S", 20260922
    )
    assert households.iloc[0]["household_id"] == "HH_P_TRS_EXP_V1_S_000001"
    assert persons.iloc[0]["person_id"] == "P_P_TRS_EXP_V1_S_000001_01"
    assert resources.iloc[0]["relation_id"] == "REL_S_0000001"
