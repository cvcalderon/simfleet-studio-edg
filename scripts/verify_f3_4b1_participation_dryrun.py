from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import tempfile
from pathlib import Path

import pandas as pd
import yaml

from simfleet_edg.evaluation.participation_cal_dryrun import run_synthetic_participation_dryrun

ROOT = Path.cwd()
REQUIRED_PARENT = "97691dbec1dee3bd8fbaefd240de512a161a59ad"
OVERLAY_LIST = ROOT / "docs/F3_4B1_OVERLAY_FILELIST_v1.txt"
CHECKSUMS = ROOT / "docs/F3_4B1_OVERLAY_CHECKSUMS_v1.sha256"


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], text=True).strip()


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def checksum_manifest_ok() -> bool:
    for line in CHECKSUMS.read_text().splitlines():
        if not line.strip():
            continue
        digest, rel = line.split(maxsplit=1)
        if sha256(ROOT / rel.strip()) != digest:
            return False
    return True


def main() -> None:
    expected = {line.strip() for line in OVERLAY_LIST.read_text().splitlines() if line.strip()}
    status = git("status", "--porcelain").splitlines()
    actual = {line[3:] for line in status if len(line) >= 4}
    cfg = yaml.safe_load((ROOT / "configs/f3/f3_4b1_participation_cal_runner_dryrun_v1.yaml").read_text())
    registry = pd.read_csv(ROOT / "docs/F3_3_CANDIDATE_ARTIFACT_REGISTRY_v1.csv", dtype=str)
    participation = registry.loc[registry["component"] == "DG_PARTICIPATION"]

    temp = Path(tempfile.mkdtemp(prefix="f3_4b1_verify_"))
    try:
        manifest = run_synthetic_participation_dryrun(ROOT, temp, validate_frozen_artifacts=True)
        access = json.loads((temp / "cal_access_manifest.json").read_text())
        selected = json.loads((temp / "selected_component_artifact.json").read_text())
        validation = pd.read_csv(temp / "validation.csv")
        checks = {
            "head_exact_parent": git("rev-parse", "HEAD") == REQUIRED_PARENT,
            "branch_main": git("branch", "--show-current") == "main",
            "ahead_zero": git("rev-list", "--count", "origin/main..HEAD") == "0",
            "behind_zero": git("rev-list", "--count", "HEAD..origin/main") == "0",
            "no_staged_changes": git("diff", "--cached", "--name-only") == "",
            "overlay_scope_exact": actual == expected,
            "overlay_checksums_exact": checksum_manifest_ok(),
            "candidate_artifacts_exact_8": len(participation) == 8,
            "candidate_train_state_exact": set(participation["train_state"]) == {"FITTED_TRAIN_ONLY_NOT_SELECTED"},
            "dryrun_status_pass": manifest["status"] == "PASS",
            "synthetic_only": manifest["data_source"] == "SYNTHETIC_ONLY",
            "cal_rows_read_zero": manifest["cal_rows_read"] == 0 and access["cal_rows_read"] == 0,
            "test_rows_read_zero": manifest["test_rows_read"] == 0 and access["test_rows_read"] == 0,
            "no_cal_files_opened": access["cal_files_opened"] == [],
            "no_test_files_opened": access["test_files_opened"] == [],
            "candidate_selection_none": manifest["candidate_selection"] == "NONE" and selected["candidate_selection"] == "NONE",
            "downstream_not_authorized": selected["authorized_for_downstream"] is False,
            "validation_all_pass": set(validation["status"]) == {"PASS"},
            "test_still_sealed": cfg["test_partition"] == "SEALED" and cfg["test_open_authorized"] is False,
            "formal_g2_not_evaluated": cfg["formal_g2"] == "NOT_EVALUATED",
        }
    finally:
        shutil.rmtree(temp, ignore_errors=True)

    failed = [name for name, value in checks.items() if not value]
    result = {
        "phase": "F3.4b-1",
        "status": "PASS" if not failed else "FAIL",
        "synthetic_dryrun_gate": "PASS" if not failed else "FAIL",
        "checks": checks,
        "failed": failed,
        "candidate_artifacts": 8,
        "cal_rows_read": 0,
        "test_rows_read": 0,
        "candidate_selection": "NONE",
        "next_component_authorized": False,
        "real_cal_open_authorized": False,
        "test_open_authorized": False,
        "formal_g2": "NOT_EVALUATED",
        "next_step_if_pass": "PREPARE_F3.4b-2_CONTROLLED_REAL_CAL_DG_PARTICIPATION",
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
