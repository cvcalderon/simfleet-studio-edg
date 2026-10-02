from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
VERIFIER = ROOT / "scripts/verify_f3_4f2b_runbundle.py"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    digest.update(path.read_bytes())
    return digest.hexdigest()


def test_runbundle_verifier_serializes_pandas_boolean(tmp_path: Path) -> None:
    manifest = {
        "status": "PASS",
        "phase": "F3.4f-2b",
        "candidate_artifacts": 5,
        "cal_rows_read_total_physical": 2873,
        "cal_isolated_raw_rows": 1147,
        "cal_sensitivity_rows": 1257,
        "joint_cal_gate_authorized": False,
        "test_rows_read": 0,
        "test_open_authorized": False,
        "formal_g2": "NOT_EVALUATED",
        "proposed_selected_artifact_id": "DIST_REF_REFERENCE",
    }
    selected = {"authorized_for_downstream": False}

    (tmp_path / "run_manifest.json").write_text(
        json.dumps(manifest), encoding="utf-8"
    )
    (tmp_path / "selected_component_artifact.json").write_text(
        json.dumps(selected), encoding="utf-8"
    )
    pd.DataFrame([{"check": "synthetic", "status": "PASS"}]).to_csv(
        tmp_path / "validation.csv", index=False
    )

    checksum_lines = []
    for name in (
        "run_manifest.json",
        "selected_component_artifact.json",
        "validation.csv",
    ):
        path = tmp_path / name
        checksum_lines.append(f"{_sha256(path)}  {name}")
    (tmp_path / "checksums.sha256").write_text(
        "\n".join(checksum_lines) + "\n", encoding="utf-8"
    )

    completed = subprocess.run(
        [sys.executable, str(VERIFIER), "--run-dir", str(tmp_path)],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout)
    assert payload["status"] == "PASS"
    assert payload["runbundle_gate"] == "PASS"
    assert payload["checks"]["validation_all_pass"] is True
