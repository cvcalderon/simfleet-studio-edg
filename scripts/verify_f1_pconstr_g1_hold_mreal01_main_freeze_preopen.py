#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import zipfile
from pathlib import Path

import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[1]
CFG = ROOT / "configs/f1/f1_pconstr_g1_hold_mreal01_main_freeze_v1.yaml"
AUDIT = ROOT / "docs/F1_PCONSTR_G1_HOLD_MREAL01_MAIN_AUDIT_v1.json"
CORE_SNAPSHOT = ROOT / "docs/F1_PCONSTR_G1_HOLD_MREAL01_CORE_HASHES_A1_SNAPSHOT_v1.json"
MANIFEST_SNAPSHOT = ROOT / "docs/F1_PCONSTR_G1_HOLD_MREAL01_RUN_MANIFEST_A1_SNAPSHOT_v1.json"
SUMMARY_SNAPSHOT = ROOT / "docs/F1_PCONSTR_G1_HOLD_MREAL01_CANDIDATE_SUMMARY_A1_SNAPSHOT_v1.csv"
FILELIST = ROOT / "docs/F1_PCONSTR_G1_HOLD_MREAL01_FREEZE_OVERLAY_FILELIST_v1.txt"
PARENT = "57891354e314df7bb38cd5b3f9e020f762826c49"
RUN_ZIP_SHA256 = "00b440d58b2c4f7f5484e8260a43f1fb9f2ce69c0b5d5c23a6272aa3b2afa505"
RUN_ZIP_SIZE = 10345871
AUTH_SHA256 = "baa10be37bf4735fe06d0cf25e0afdcf7a83f51b5352d6ea1305b7a651be0911"
SELECTED = "P_CONSTR_RMIN_V2_HD_U"

CORE_FILES = {
    "households": f"M_{SELECTED}_households.csv",
    "persons": f"M_{SELECTED}_persons.csv",
    "resources": f"M_{SELECTED}_resources.csv",
    "projected_cube_M": "projected_cube_M.csv",
    "h6_households_M": "h6_households_M.csv",
    "equivalence_plan_M": "equivalence_plan_M.csv",
    "equivalence_class_fit_M": "equivalence_class_fit_M.csv",
}


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def verify_internal_checksums(run: Path) -> bool:
    manifest = run / "checksums.sha256"
    if not manifest.is_file():
        return False
    for line in manifest.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        expected, rel = line.split(maxsplit=1)
        path = run / rel.strip()
        if not path.is_file() or sha256_file(path) != expected:
            return False
    return True


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--run-zip", required=True)
    parser.add_argument("--authorization-json", required=True)
    args = parser.parse_args()

    run = Path(args.run_dir).expanduser().resolve()
    run_zip = Path(args.run_zip).expanduser().resolve()
    auth = Path(args.authorization_json).expanduser().resolve()

    cfg = yaml.safe_load(CFG.read_text(encoding="utf-8"))
    audit = json.loads(AUDIT.read_text(encoding="utf-8"))
    expected_core = json.loads(CORE_SNAPSHOT.read_text(encoding="utf-8"))
    expected_manifest = json.loads(MANIFEST_SNAPSHOT.read_text(encoding="utf-8"))
    expected_summary = pd.read_csv(SUMMARY_SNAPSHOT).iloc[0].to_dict()

    actual_scope = {line[3:] for line in git("status", "--short").splitlines() if line}
    expected_scope = set(FILELIST.read_text(encoding="utf-8").splitlines())

    manifest = json.loads((run / "run_manifest.json").read_text(encoding="utf-8"))
    core = json.loads((run / "core_hashes.json").read_text(encoding="utf-8"))
    summary = pd.read_csv(run / "candidate_summary_M.csv").iloc[0].to_dict()
    validation = pd.read_csv(run / "validation.csv")

    actual_core_file_hashes = {
        key: sha256_file(run / rel) for key, rel in CORE_FILES.items()
    }

    with zipfile.ZipFile(run_zip) as zf:
        zip_integrity = zf.testzip() is None
        zip_file_count = len([i for i in zf.infolist() if not i.is_dir()])

    checks = {
        "head_exact_parent": git("rev-parse", "HEAD") == PARENT,
        "branch_main": git("branch", "--show-current") == "main",
        "origin_exact_parent": git("rev-parse", "origin/main") == PARENT,
        "no_staged_changes": git("diff", "--cached", "--name-only") == "",
        "overlay_scope_exact": actual_scope == expected_scope,
        "run_zip_hash_exact": run_zip.is_file() and sha256_file(run_zip) == RUN_ZIP_SHA256,
        "run_zip_size_exact": run_zip.is_file() and run_zip.stat().st_size == RUN_ZIP_SIZE,
        "run_zip_integrity": zip_integrity,
        "run_zip_file_count_12": zip_file_count == 12,
        "run_internal_checksums": verify_internal_checksums(run),
        "authorization_hash_exact": auth.is_file() and sha256_file(auth) == AUTH_SHA256,
        "run_manifest_snapshot_exact": manifest == expected_manifest,
        "core_hash_snapshot_exact": core == expected_core,
        "core_files_match_core_hashes": actual_core_file_hashes == expected_core,
        "candidate_summary_snapshot_exact": all(str(summary[k]) == str(v) for k, v in expected_summary.items()),
        "validation_10_all_pass": len(validation) == 10 and bool(validation["status"].eq("PASS").all()),
        "candidate_exact": manifest["selected_candidate"] == SELECTED,
        "scale_M_exact": manifest["scale_id"] == "M",
        "runner_commit_exact": manifest["git_commit"] == PARENT,
        "candidate_seed_exact": manifest["candidate_master_seed"] == 20261005,
        "h6_seed_exact": manifest["h6_master_seed"] == 20261004,
        "mreal_proposed_resolved": manifest["hold_mreal_001"] == "PROPOSED_RESOLVED_AWAITING_MAIN_FREEZE",
        "hold_thresh_open": manifest["hold_thresh_001"] == "OPEN",
        "holdout_unacquired": manifest["holdout_1000A_1035_acquired"] is False,
        "holdout_unread": manifest["holdout_1000A_1035_values_read"] is False,
        "holdout_not_evaluated": manifest["holdout_metric_evaluation"] is False,
        "cal_closed": manifest["cal_reopened"] is False,
        "test_closed": manifest["mid_test_reopened"] is False,
        "plr_closed": manifest["spatial_plr_allocation"] is False,
        "f3_closed": manifest["f3_modified"] is False,
        "G1_open": manifest["G1"] == "OPEN",
        "G2_closed": manifest["G2"] == "PASS_CLOSED_DO_NOT_REOPEN",
        "freeze_config_parent_exact": cfg["required_parent_commit"] == PARENT,
        "freeze_status_resolved": cfg["status_after_commit"] == "HOLD_MREAL_001_RESOLVED_FROZEN",
        "audit_accepts": audit["status"] == "PASS" and audit["decision"] == "ACCEPT_FOR_MAIN_FREEZE",
    }

    failed = [name for name, ok in checks.items() if not bool(ok)]
    payload = {
        "phase": "F1-P_CONSTR-G1-HOLD-MREAL-001 MAIN FREEZE PREOPEN",
        "status": "PASS" if not failed else "FAIL",
        "parent": PARENT,
        "runbundle_zip_sha256": RUN_ZIP_SHA256,
        "authorization_json_sha256": AUTH_SHA256,
        "selected_candidate": SELECTED,
        "scale_id": "M",
        "checks": {k: bool(v) for k, v in checks.items()},
        "failed": failed,
        "controlled_state_after_commit": {
            "HOLD_MREAL_001": "RESOLVED_FROZEN",
            "HOLD_THRESH_001": "OPEN",
            "holdout_1000A_1035_acquired": False,
            "holdout_1000A_1035_values_read": False,
            "holdout_1000A_1035_authorized": False,
            "G1": "OPEN",
            "G2": "PASS_CLOSED_DO_NOT_REOPEN",
        },
        "next_step_if_pass": "COMMIT_AND_PUSH_HOLD_MREAL01_MAIN_FREEZE",
    }
    print(json.dumps(payload, indent=2, sort_keys=True))
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
