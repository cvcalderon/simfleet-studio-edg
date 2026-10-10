from __future__ import annotations

from pathlib import Path

from simfleet_edg.repro.f4_2b_a_local_sensitivity import PROPOSAL_COLUMNS, safe_path
from simfleet_edg.spatial.escort_synthetic_relations import load_variants


def test_run_contract_and_no_extras() -> None:
    root = Path(__file__).resolve().parents[1]
    allowed = (root / "docs/F4_2B_A_LOCAL_OVERLAY_FILELIST_v1.txt").read_text().splitlines()
    assert len(allowed) == 20 and len(set(allowed)) == 20
    assert "target_person_id" in PROPOSAL_COLUMNS
    assert "household_size_class" in PROPOSAL_COLUMNS
    assert "resource_state" in PROPOSAL_COLUMNS
    assert "mode" not in PROPOSAL_COLUMNS
    rows = load_variants(root / "docs/F4_2B_A_LOCAL_VARIANT_MATRIX_v1.csv")
    assert len(rows) == 10
    assert [(v.year, v.p_household) for v in rows][:2] == [("2018", 0.0), ("2018", .25)]


def test_frozen_filename_and_forbidden_data(tmp_path: Path) -> None:
    p = tmp_path / "input"
    assert safe_path(p) == p.absolute()
    import pytest
    with pytest.raises(ValueError, match="Forbidden"):
        safe_path(tmp_path / "MiD_TEST/secret.csv")
