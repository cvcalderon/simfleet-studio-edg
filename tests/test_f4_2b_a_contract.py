from __future__ import annotations

import csv
import hashlib
from pathlib import Path

import yaml  # type: ignore[import-untyped]


def test_frozen_config_and_preregistered_matrix() -> None:
    root = Path(__file__).resolve().parents[1]
    c = yaml.safe_load((root / "configs/f4/f4_2b_a_local_sensitivity_preopen_v1.yaml").read_text())
    assert c["evidence_class"] == "SYNTHETIC_HYPOTHETICAL_NOT_OBSERVED"
    assert c["selected_spatial_policy"] == "S_DIST"
    assert len(c["runbundle_sha256"]) == 39
    assert c["allowed_variant_count"] == 11
    path = root / "docs/F4_2B_A_LOCAL_VARIANT_MATRIX_v1.csv"
    with path.open(newline="") as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 10
    assert {(r["year"], r["p_household_hypothesis"]) for r in rows} == {
        (y, p) for y in ("2018", "2023") for p in ("0.00", "0.25", "0.50", "0.75", "1.00")}
    assert hashlib.sha256(path.read_bytes()).hexdigest() == c["source_files_sha256"][path.name]
