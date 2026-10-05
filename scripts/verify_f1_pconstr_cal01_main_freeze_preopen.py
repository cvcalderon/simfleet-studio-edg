#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import subprocess
import sys
import zipfile
from decimal import Decimal
from pathlib import Path

import yaml

PARENT = "c8c4e1b3e479bff3ec9351998d2d880c3ec00c50"
RUN_SHA = "672ef2032ff80080e8b03a59b11f34505556b76a53177bdbe28ed508fe61b839"
SELECTED = "P_CONSTR_RMIN_V2_HD_U"

OVERLAY_FILES = [
    "configs/f1/f1_pconstr_cal01_main_freeze_v1.yaml",
    "docs/F1_PCONSTR_CAL01_MAIN_AUDIT_v1.json",
    "docs/F1_PCONSTR_CAL01_SELECTION_v1.json",
    "docs/F1_PCONSTR_G1_THRESHOLDS_v1.csv",
    "docs/F1_PCONSTR_CAL01_FAMILY_METRICS_A1_SNAPSHOT_v1.csv",
    "docs/F1_PCONSTR_CAL01_FAMILY_SUBMETRICS_A1_SNAPSHOT_v1.csv",
    "docs/F1_PCONSTR_CAL01_VALIDATION_A1_SNAPSHOT_v1.csv",
    "docs/F1_PCONSTR_CAL01_CAL_ACCESS_A1_SNAPSHOT_v1.json",
    "docs/F1_PCONSTR_CAL01_MAIN_FREEZE_v1.md",
    "scripts/verify_f1_pconstr_cal01_main_freeze_preopen.py",
    "tests/test_f1_pconstr_cal01_main_freeze.py",
    "docs/F1_PCONSTR_CAL01_FREEZE_OVERLAY_CHECKSUMS_v1.sha256",
    "docs/F1_PCONSTR_CAL01_FREEZE_OVERLAY_FILELIST_v1.txt",
]

def git(repo: Path, *args: str) -> str:
    return subprocess.check_output(["git", "-C", str(repo), *args], text=True).strip()

def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()

def read_zip(z: zipfile.ZipFile, rel: str) -> bytes:
    roots = {n.split("/", 1)[0] for n in z.namelist() if "/" in n}
    if len(roots) != 1:
        raise AssertionError(f"Unexpected zip roots: {sorted(roots)}")
    root = next(iter(roots))
    return z.read(f"{root}/{rel}")

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo-root", type=Path, default=Path.cwd())
    ap.add_argument("--runbundle", type=Path, required=True)
    args = ap.parse_args()
    repo = args.repo_root.resolve()
    runbundle = args.runbundle.resolve()

    cfg = yaml.safe_load((repo / "configs/f1/f1_pconstr_cal01_main_freeze_v1.yaml").read_text())
    audit = json.loads((repo / "docs/F1_PCONSTR_CAL01_MAIN_AUDIT_v1.json").read_text())
    selection_freeze = json.loads((repo / "docs/F1_PCONSTR_CAL01_SELECTION_v1.json").read_text())
    access_snap = json.loads((repo / "docs/F1_PCONSTR_CAL01_CAL_ACCESS_A1_SNAPSHOT_v1.json").read_text())

    changed = set(filter(None, git(repo, "status", "--porcelain").splitlines()))
    changed_paths = sorted(line[3:] for line in changed)
    staged = git(repo, "diff", "--cached", "--name-only").splitlines()

    checks = {}
    checks["branch_main"] = git(repo, "branch", "--show-current") == "main"
    checks["parent_head"] = git(repo, "rev-parse", "HEAD") == PARENT
    checks["origin_main_parent"] = git(repo, "rev-parse", "origin/main") == PARENT
    checks["no_staged_changes"] = staged == []
    checks["overlay_scope_exact"] = set(changed_paths) == set(OVERLAY_FILES)

    # Overlay checksum manifest.
    manifest = repo / "docs/F1_PCONSTR_CAL01_FREEZE_OVERLAY_CHECKSUMS_v1.sha256"
    manifest_ok = True
    for line in manifest.read_text().splitlines():
        expected, rel = line.split(maxsplit=1)
        if sha256(repo / rel.strip()) != expected:
            manifest_ok = False
    checks["overlay_checksums_pass"] = manifest_ok

    checks["runbundle_sha_exact"] = runbundle.is_file() and sha256(runbundle) == RUN_SHA

    if checks["runbundle_sha_exact"]:
        with zipfile.ZipFile(runbundle) as z:
            # Internal checksums
            internal_ok = True
            checksum_text = read_zip(z, "checksums.sha256").decode()
            for line in checksum_text.splitlines():
                expected, rel = line.split(maxsplit=1)
                if hashlib.sha256(read_zip(z, rel.strip())).hexdigest() != expected:
                    internal_ok = False
            checks["runbundle_internal_checksums"] = internal_ok

            rm = json.loads(read_zip(z, "run_manifest.json"))
            ca = json.loads(read_zip(z, "cal_access_manifest.json"))
            sp = json.loads(read_zip(z, "selection_proposal.json"))
            issues = list(csv.DictReader(io.StringIO(read_zip(z, "issues.csv").decode())))
            fam = list(csv.DictReader(io.StringIO(read_zip(z, "family_metrics.csv").decode())))
            thr = list(csv.DictReader(io.StringIO(read_zip(z, "thresholds_proposed.csv").decode())))

            checks["runbundle_status_pass"] = rm["status"] == "PASS"
            checks["runner_commit_exact"] = rm["git_commit"] == PARENT
            checks["issues_empty"] = len(issues) == 0
            checks["test_zero"] = rm["test_rows_materialized"] == 0 == ca["test_rows_materialized"]
            checks["holdout_unread"] = rm["holdout_1000A_1035_read"] is False and ca["holdout_1000A_1035_read"] is False
            checks["plr_closed"] = rm["spatial_plr_allocation"] is False
            checks["f3_closed"] = rm["f3_modified"] is False
            checks["cal_counts_exact"] = (
                ca["split_cal_households_all"] == 268
                and ca["split_cal_households_strict"] == 263
                and ca["private_cal_households_materialized"] == 267
                and ca["private_cal_person_rows_materialized"] == 470
            )

            # Snapshot exactness.
            checks["family_metrics_snapshot_exact"] = read_zip(z, "family_metrics.csv") == (repo / "docs/F1_PCONSTR_CAL01_FAMILY_METRICS_A1_SNAPSHOT_v1.csv").read_bytes()
            checks["family_submetrics_snapshot_exact"] = read_zip(z, "family_submetrics.csv") == (repo / "docs/F1_PCONSTR_CAL01_FAMILY_SUBMETRICS_A1_SNAPSHOT_v1.csv").read_bytes()
            checks["validation_snapshot_exact"] = read_zip(z, "validation.csv") == (repo / "docs/F1_PCONSTR_CAL01_VALIDATION_A1_SNAPSHOT_v1.csv").read_bytes()
            checks["access_snapshot_exact"] = ca == access_snap

            tau = {r["family_id"]: Decimal(r["tau_proposed"]) for r in thr}
            err = {(r["variant_id"], r["family_id"]): Decimal(r["error"]) for r in fam}

            w_material = []
            w_degrade = []
            u_degrade_ptrs = []
            for family, t in tau.items():
                eu = err[("P_CONSTR_RMIN_V2_HD_U", family)]
                ew = err[("P_CONSTR_RMIN_V2_HD_W", family)]
                ep = err[("P_TRS_V1_FINAL", family)]
                w_material.append(eu - ew > t)
                w_degrade.append(ew - eu > t)
                u_degrade_ptrs.append(eu - ep > t)

            stage1 = "P_CONSTR_RMIN_V2_HD_W" if any(w_material) and not any(w_degrade) else "P_CONSTR_RMIN_V2_HD_U"
            stage2 = stage1 if (350 < 3968 and 4 <= 29 and not any(u_degrade_ptrs)) else "P_TRS_V1_FINAL"

            checks["selection_rederived"] = stage1 == SELECTED and stage2 == SELECTED
            checks["proposal_matches"] = (
                sp["stage_1_constrained_proposal"] == SELECTED
                and sp["stage_2_final_candidate_proposal"] == SELECTED
            )

            frozen_thr = list(csv.DictReader((repo / "docs/F1_PCONSTR_G1_THRESHOLDS_v1.csv").open()))
            frozen_tau = {r["family_id"]: Decimal(r["tau"]) for r in frozen_thr}
            checks["thresholds_exact"] = frozen_tau == tau
    else:
        for key in [
            "runbundle_internal_checksums","runbundle_status_pass","runner_commit_exact","issues_empty",
            "test_zero","holdout_unread","plr_closed","f3_closed","cal_counts_exact",
            "family_metrics_snapshot_exact","family_submetrics_snapshot_exact","validation_snapshot_exact",
            "access_snapshot_exact","selection_rederived","proposal_matches","thresholds_exact"
        ]:
            checks[key] = False

    checks["freeze_candidate_exact"] = selection_freeze["selected_candidate"] == SELECTED
    checks["audit_pass"] = audit["status"] == "PASS" and audit["decision"] == "ACCEPT_FOR_MAIN_FREEZE"
    checks["g1_open"] = cfg["boundaries"]["G1"] == "OPEN"
    checks["g2_closed"] = cfg["boundaries"]["G2"] == "PASS_CLOSED_DO_NOT_REOPEN"
    checks["holdout_not_authorized"] = cfg["boundaries"]["holdout_1000A_1035_authorized"] is False
    checks["cal_not_independent_validation"] = cfg["boundaries"]["cal_reuse_as_independent_validation"] is False

    failed = [k for k,v in checks.items() if not v]
    out = {
        "phase":"F1-P_CONSTR-CAL-01 MAIN FREEZE PREOPEN",
        "parent":PARENT,
        "runbundle_sha256":RUN_SHA,
        "selected_candidate":SELECTED,
        "checks":checks,
        "changed_paths":changed_paths,
        "failed":failed,
        "status":"PASS" if not failed else "FAIL",
        "next_step_if_pass":"COMMIT_AND_PUSH_CAL01_MAIN_FREEZE_THEN_SEPARATE_1000A_1035_PREOPEN"
    }
    print(json.dumps(out, indent=2, sort_keys=True))
    return 0 if not failed else 1

if __name__ == "__main__":
    sys.exit(main())
