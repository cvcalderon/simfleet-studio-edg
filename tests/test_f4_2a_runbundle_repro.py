from __future__ import annotations

import hashlib
import json
import runpy
from pathlib import Path
from typing import cast

import pytest


def _verify(root: Path) -> dict[str, object]:
    code = runpy.run_path(str(Path(__file__).resolve().parents[1] /
                               "scripts/verify_f4_2a_runbundle.py"), run_name="f4_2a_verifier")
    return cast(dict[str, object], code["verify_runbundle"](root))


def test_runbundle_rejects_corrupted_file(tmp_path: Path) -> None:
    (tmp_path / "spatial_1").mkdir()
    (tmp_path / "spatial_2").mkdir()
    for name in ("spatial_1/a.csv.gz", "spatial_2/a.csv.gz"):
        path = tmp_path / name
        path.write_bytes(b"stable data")
    hashes = {name: hashlib.sha256((tmp_path / name).read_bytes()).hexdigest()
              for name in ("spatial_1/a.csv.gz", "spatial_2/a.csv.gz")}
    (tmp_path / "runbundle_sha256.json").write_text(json.dumps(hashes))
    (tmp_path / "run_manifest.json").write_text(json.dumps({
        "status": "RETURN_TO_MAIN", "full_dgen_A_B_exact": True,
        "spatial_two_run_exact": True, "g3_opened": False,
        "cal_reads": 0, "mid_test_reads": 0,
        "scenario": {"persons": 100000}, "candidate_promotable_internal_only": False,
    }))
    assert _verify(tmp_path)["status"] == "PASS"
    (tmp_path / "spatial_2/a.csv.gz").write_bytes(b"corrupted")
    with pytest.raises(ValueError, match="SHA-256 mismatch"):
        _verify(tmp_path)
