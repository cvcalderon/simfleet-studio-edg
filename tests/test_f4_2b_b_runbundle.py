"""Fail closed on partial or mismatched downstream evidence."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_verifier_rejects_unproven_scientific_claim(tmp_path: Path) -> None:
    path = ROOT / "scripts/verify_f4_2b_b_runbundle.py"
    spec = importlib.util.spec_from_file_location("bundle_verifier", path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    (tmp_path / "run_manifest_v1.json").write_text(json.dumps({
        "status": "RETURN_TO_MAIN_NO_G3", "science_class": "OBSERVED_CO_TRAVEL",
        "variant_ids": [], "two_independent_runs_byte_exact": True,
        "g3_opened": False, "f4_2c_opened": False}))
    with pytest.raises(RuntimeError, match="BUNDLE_PROVENANCE"):
        mod.verify(tmp_path)
