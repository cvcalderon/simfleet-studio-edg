#!/usr/bin/env python3
"""Verify the preserved F1-P_CONSTR-IMPL-01 A1 RunBundle for MAIN freeze."""
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
CFG = ROOT / "configs/f1/f1_pconstr_impl01_a1_freeze_v1.yaml"
AUDIT_SNAPSHOT = ROOT / "docs/F1_PCONSTR_IMPL01_RECONCILIATION_A1_SNAPSHOT_v1.csv"
VALIDATION_SNAPSHOT = ROOT / "docs/F1_PCONSTR_IMPL01_VALIDATION_A1_SNAPSHOT_v1.csv"
FILELIST = ROOT / "docs/F1_PCONSTR_IMPL01_FREEZE_OVERLAY_FILELIST_v1.txt"
CHECKSUMS = ROOT / "docs/F1_PCONSTR_IMPL01_FREEZE_OVERLAY_CHECKSUMS_v1.sha256"
PARENT = "2b08eeb1440c1fd8171917b91047b1b0c6be46f6"
RUN_ZIP_SHA256 = "de4e70a07483f594053c2bb6b04e82e8be8d38191e0336bebad3e38186175de0"
EXPECTED_RUN_FILES = {
    "checksums.sha256",
    "config_snapshot.yaml",
    "manifest.json",
    "normalized_sources.csv",
    "performance.csv",
    "reconciled_person_cube.csv",
    "reconciliation_audit.csv",
    "run.log",
    "validation.csv",
}
EXPECTED_SOURCE_COUNTS = {
    "1000A-1029": 84,
    "1000A-2070": 840,
    "1000A-2071": 252,
    "1000A-3082": 3024,
    "5000H-1001": 84,
}
SIZE_MAP = {"PERSON01": 1, "PERSON02": 2, "PERSON03": 3, "PERSON04": 4, "PERSON05": 5}


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def verify_checksum_manifest(directory: Path, manifest_name: str) -> bool:
    manifest = directory / manifest_name
    if not manifest.is_file():
        return False
    for line in manifest.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        expected, rel = line.split(maxsplit=1)
        path = directory / rel.strip()
        if not path.is_file() or sha256_file(path) != expected:
            return False
    return True


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--run-zip", required=True)
    args = parser.parse_args()

    run = Path(args.run_dir).expanduser().resolve()
    run_zip = Path(args.run_zip).expanduser().resolve()
    cfg = yaml.safe_load(CFG.read_text(encoding="utf-8"))
    manifest = json.loads((run / "manifest.json").read_text(encoding="utf-8"))
    normalized = pd.read_csv(run / "normalized_sources.csv", keep_default_na=False)
    cube = pd.read_csv(run / "reconciled_person_cube.csv", keep_default_na=False)
    audit = pd.read_csv(run / "reconciliation_audit.csv")
    validation = pd.read_csv(run / "validation.csv")
    performance = pd.read_csv(run / "performance.csv")
    config_bytes = (run / "config_snapshot.yaml").read_bytes()
    run_config = yaml.safe_load(config_bytes)

    actual_run_files = {p.name for p in run.iterdir() if p.is_file()}
    source_counts = normalized.groupby("table_id").size().astype(int).to_dict()

    stage1 = int((cube["fit_target_value"] - cube["published_value"]).abs().sum())
    changed = int((cube["fit_target_value"] != cube["published_value"]).sum())
    max_adjustment = int((cube["fit_target_value"] - cube["published_value"]).abs().max())

    n1029 = normalized.loc[
        (normalized["table_id"] == "1000A-1029") & normalized["HSHGR2_code"].ne("")
    ].copy()
    m2 = cube.groupby(["bezirk_code", "household_size_code"], as_index=False)["fit_target_value"].sum()
    t2 = n1029[["GEOBZ1_code", "HSHGR2_code", "published_value"]].rename(
        columns={"GEOBZ1_code": "bezirk_code", "HSHGR2_code": "household_size_code", "published_value": "target"}
    )
    m2 = m2.merge(t2, on=["bezirk_code", "household_size_code"], validate="one_to_one")
    stage2 = int((m2["fit_target_value"] - m2["target"]).abs().sum())

    n2071 = normalized.loc[
        (normalized["table_id"] == "1000A-2071")
        & normalized["HSHGR2_code"].ne("")
        & normalized["GESCH1_code"].ne("")
    ].copy()
    m3 = cube.groupby(["bezirk_code", "sex_code", "household_size_code"], as_index=False)["fit_target_value"].sum()
    t3 = n2071[["GEOBZ1_code", "GESCH1_code", "HSHGR2_code", "published_value"]].rename(
        columns={
            "GEOBZ1_code": "bezirk_code",
            "GESCH1_code": "sex_code",
            "HSHGR2_code": "household_size_code",
            "published_value": "target",
        }
    )
    m3 = m3.merge(t3, on=["bezirk_code", "sex_code", "household_size_code"], validate="one_to_one")
    stage3 = int((m3["fit_target_value"] - m3["target"]).abs().sum())

    cube_totals = cube.groupby("bezirk_code")["fit_target_value"].sum().astype(int)
    audit_totals = audit.set_index("bezirk_code")["published_total_persons_1029"].astype(int)

    aggregate = cube.groupby(["bezirk_code", "household_size_code"])["fit_target_value"].sum().astype(int)
    divisibility_violations = 0
    for (_bezirk, hh_code), value in aggregate.items():
        if hh_code in SIZE_MAP and int(value) % SIZE_MAP[hh_code] != 0:
            divisibility_violations += 1

    published_zero_mask = cube["published_raw"].eq("-")
    published_zero_count = int(published_zero_mask.sum())
    published_zero_violations = int(
        (published_zero_mask & cube["fit_target_value"].ne(0)).sum()
    )

    expected_scope = set(FILELIST.read_text(encoding="utf-8").splitlines())
    actual_scope = {line[3:] for line in git("status", "--short").splitlines() if line}

    checks = {
        "head_exact_parent": git("rev-parse", "HEAD") == PARENT,
        "branch_main": git("branch", "--show-current") == "main",
        "ahead_zero": git("rev-list", "--count", "origin/main..HEAD") == "0",
        "behind_zero": git("rev-list", "--count", "HEAD..origin/main") == "0",
        "no_staged_changes": git("diff", "--cached", "--name-only") == "",
        "overlay_scope_exact": actual_scope == expected_scope,
        "overlay_checksums_pass": verify_checksum_manifest(ROOT, "docs/F1_PCONSTR_IMPL01_FREEZE_OVERLAY_CHECKSUMS_v1.sha256"),
        "run_zip_hash_exact": run_zip.is_file() and sha256_file(run_zip) == RUN_ZIP_SHA256,
        "run_zip_integrity": run_zip.is_file() and zipfile.ZipFile(run_zip).testzip() is None,
        "run_files_exact": actual_run_files == EXPECTED_RUN_FILES,
        "run_checksums_pass": verify_checksum_manifest(run, "checksums.sha256"),
        "manifest_schema_exact": manifest["schema_version"] == "simfleet-edg-f1-pconstr-impl01-runbundle-v1",
        "manifest_phase_exact": manifest["phase_id"] == "F1-P_CONSTR-IMPL-01",
        "manifest_status_pass": manifest["status"] == "PASS",
        "execution_commit_exact": manifest["git"]["commit"] == PARENT,
        "execution_branch_main": manifest["git"]["branch"] == "main",
        "execution_worktree_clean": bool(manifest["git"]["worktree_clean"]),
        "execution_ahead_zero": int(manifest["git"]["ahead"]) == 0,
        "execution_behind_zero": int(manifest["git"]["behind"]) == 0,
        "config_snapshot_hash_exact": hashlib.sha256(config_bytes).hexdigest() == manifest["config_sha256"],
        "algorithm_exact": run_config["reconciliation"]["algorithm_id"] == "EDG_RECONCILED_PHH_PERSON_CUBE_V1",
        "stage4_exact": run_config["reconciliation"]["stage4_tie_break"] == "CANONICAL_WEIGHTED_LINEAR_V1",
        "source_counts_exact": source_counts == EXPECTED_SOURCE_COUNTS,
        "normalized_rows_4284": len(normalized) == 4284,
        "cube_rows_1584": len(cube) == 1584,
        "cube_bezirke_12": cube["bezirk_code"].nunique() == 12,
        "cube_key_unique": not cube.duplicated(["bezirk_code", "age_zensus_11_source_code", "sex_code", "household_size_code"]).any(),
        "cube_nonnegative": bool(cube["fit_target_value"].ge(0).all()),
        "stage1_rederived_161": stage1 == 161,
        "changed_rederived_56": changed == 56,
        "max_adjustment_rederived_12": max_adjustment == 12,
        "stage2_rederived_272": stage2 == 272,
        "stage3_rederived_478": stage3 == 478,
        "person_total_3532081": int(cube["fit_target_value"].sum()) == 3532081,
        "exact_bezirk_totals": bool(cube_totals.equals(audit_totals)),
        "published_zero_cells_38": published_zero_count == 38,
        "published_zero_violations_zero": published_zero_violations == 0,
        "aggregate_divisibility_sizes_1_to_5": divisibility_violations == 0,
        "audit_rows_12": len(audit) == 12,
        "audit_all_feasible": bool(audit["feasible"].all()),
        "validation_snapshot_exact": validation.equals(pd.read_csv(VALIDATION_SNAPSHOT)),
        "audit_snapshot_exact": audit.equals(pd.read_csv(AUDIT_SNAPSHOT)),
        "validation_all_pass": bool(validation["status"].eq("PASS").all()),
        "performance_single_positive": len(performance) == 1 and float(performance.iloc[0]["wall_seconds"]) > 0,
        "raw_sources_not_copied": bool(manifest["policy"]["raw_source_bytes_copied_into_runbundle"] is False),
        "source_bytes_not_modified": bool(manifest["policy"]["source_bytes_modified"] is False),
        "calibration_not_read": bool(manifest["policy"]["calibration_read"] is False),
        "test_not_read": bool(manifest["policy"]["test_read"] is False),
        "f3_not_modified": bool(manifest["policy"]["f3_modified"] is False),
        "freeze_calibration_unread": cfg["boundaries"]["calibration_read"] is False,
        "freeze_holdout_unread": cfg["boundaries"]["holdout_1000A_1035_read"] is False,
        "g1_open": cfg["project_gates"]["G1"] == "OPEN",
        "g2_closed": cfg["project_gates"]["G2"] == "PASS_CLOSED_DO_NOT_REOPEN",
    }

    failed = [name for name, value in checks.items() if not bool(value)]
    payload = {
        "phase": "F1-P_CONSTR-IMPL-01",
        "status": "PASS" if not failed else "FAIL",
        "freeze_gate": "PASS" if not failed else "FAIL",
        "implementation_commit": PARENT,
        "runbundle_zip_sha256": RUN_ZIP_SHA256,
        "rederived": {
            "normalized_rows": len(normalized),
            "person_domain_total": int(cube["fit_target_value"].sum()),
            "bezirk_count": int(cube["bezirk_code"].nunique()),
            "detail_cells": len(cube),
            "detail_cells_changed": changed,
            "stage1_l1_total": stage1,
            "stage2_l1_total": stage2,
            "stage3_l1_total": stage3,
            "max_detailed_abs_adjustment": max_adjustment,
            "published_zero_cells": published_zero_count,
            "published_zero_violations": published_zero_violations,
            "aggregate_divisibility_violations_sizes_1_to_5": divisibility_violations,
        },
        "formal_g1": "OPEN",
        "formal_g2": "PASS_CLOSED_DO_NOT_REOPEN",
        "checks": {name: bool(value) for name, value in checks.items()},
        "failed": failed,
        "next_step_if_pass": "COMMIT_IMPL01_A1_FREEZE",
    }
    print(json.dumps(payload, indent=2, sort_keys=True))
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
