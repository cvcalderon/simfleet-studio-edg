import hashlib
import json
import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "configs/f4/f4_1c_b_acquisition_preopen_v1.yaml"
VERIFIER = ROOT / "scripts/verify_f4_1c_b_runbundle.py"


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def _make_runbundle(path: Path) -> None:
    cfg = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    required = set(cfg["required_runbundle"])
    path.mkdir()
    md5 = "a" * 32
    sha = "b" * 64
    acquisition = {
        "source_snapshot_id": "OSM_GEOFABRIK_BERLIN_2026-10-04_V1",
        "provider_md5_expected": md5,
        "provider_md5_observed": md5,
        "local_sha256": sha,
    }
    manifest = {
        "phase": "F4.1c-B",
        "status": "PASS",
        "mode": "ACQUIRE_AND_AUDIT_ONLY",
        "source_snapshot_id": "OSM_GEOFABRIK_BERLIN_2026-10-04_V1",
        "implementation_commit": "c" * 40,
        "local_sha256": sha,
        "provider_md5": md5,
        "runtime_location_supply_materialized": False,
        "residential_anchor_materialized": False,
        "home_assignments": 0,
        "destination_assignments": 0,
        "candidate_selection": "NONE",
        "g3_opened": False,
        "mid_test_read": False,
        "g1_reopened": False,
        "g2_reopened": False,
    }
    _write_json(path / "acquisition_manifest.json", acquisition)
    _write_json(path / "pbf_metadata.json", {"pbf_open_read_check": True, "pbf_header_timestamp": None, "pbf_bbox": None, "local_sha256": sha})
    _write_json(path / "environment.json", {"python": "3.12.12"})
    _write_json(path / "run_manifest.json", manifest)
    (path / "provider_md5.txt").write_text(md5 + "\n", encoding="utf-8")
    (path / "local_sha256.txt").write_text(sha + "\n", encoding="utf-8")
    (path / "F4_1C_B_AUDIT_SUMMARY.md").write_text("# audit\n", encoding="utf-8")
    (path / "run.log").write_text("ok\n", encoding="utf-8")

    csv_files = {name for name in required if name.endswith(".csv")}
    for name in csv_files:
        (path / name).write_text("status\nNO_ROWS\n", encoding="utf-8")

    assert required - {"checksums.sha256"} == {p.name for p in path.iterdir()}
    rows = []
    for target in sorted(path.iterdir()):
        digest = hashlib.sha256(target.read_bytes()).hexdigest()
        rows.append(f"{digest}  {target.name}")
    (path / "checksums.sha256").write_text("\n".join(rows) + "\n", encoding="utf-8")


def test_runbundle_verifier_accepts_complete_audit_only_bundle(tmp_path: Path) -> None:
    run = tmp_path / "run"
    _make_runbundle(run)
    completed = subprocess.run(
        [sys.executable, str(VERIFIER), str(run)],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    payload = json.loads(completed.stdout)
    assert payload["runbundle_gate"] == "PASS"


def test_runbundle_verifier_detects_checksum_tamper(tmp_path: Path) -> None:
    run = tmp_path / "run"
    _make_runbundle(run)
    (run / "run.log").write_text("tampered\n", encoding="utf-8")
    completed = subprocess.run(
        [sys.executable, str(VERIFIER), str(run)],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert completed.returncode == 1
    payload = json.loads(completed.stdout)
    assert payload["checks"]["checksums_ok"] is False
