#!/usr/bin/env python3
"""PREOPEN verifier for F1-P_CONSTR G1 HOLD-MREAL-001."""
from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

import yaml

PARENT = "faa8a024498f672f1b4e34dbd54219afef020a1a"
EXPECTED_FILES = {
    "configs/f1/f1_pconstr_g1_hold_mreal01_preopen_v1.yaml",
    "docs/F1_PCONSTR_G1_HOLD_MREAL01_EXECUTION_AUTHORIZATION_TEMPLATE_v1.json",
    "docs/F1_PCONSTR_G1_HOLD_MREAL01_OVERLAY_CHECKSUMS_v1.sha256",
    "docs/F1_PCONSTR_G1_HOLD_MREAL01_OVERLAY_FILELIST_v1.txt",
    "docs/F1_PCONSTR_G1_HOLD_MREAL01_PREOPEN_v1.md",
    "scripts/verify_f1_pconstr_g1_hold_mreal01_preopen.py",
    "src/simfleet_edg/repro/f1_pconstr_g1_hold_mreal01_runner.py",
    "tests/test_f1_pconstr_g1_hold_mreal01_preopen.py",
}


def git(root: Path, *args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=root, text=True).strip()


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    root = Path.cwd().resolve()
    cfg = yaml.safe_load(
        (root / "configs/f1/f1_pconstr_g1_hold_mreal01_preopen_v1.yaml").read_text(
            encoding="utf-8"
        )
    )
    hold = yaml.safe_load(
        (root / "configs/f1/f1_pconstr_g1_holdout_1000a_1035_preopen_v1.yaml").read_text(
            encoding="utf-8"
        )
    )
    auth = json.loads(
        (
            root / "docs/F1_PCONSTR_G1_HOLD_MREAL01_EXECUTION_AUTHORIZATION_TEMPLATE_v1.json"
        ).read_text(encoding="utf-8")
    )
    changed = set(filter(None, git(root, "status", "--porcelain").splitlines()))
    changed_paths = {line[3:] for line in changed}
    staged = git(root, "diff", "--cached", "--name-only")
    checks = {
        "parent_head": git(root, "rev-parse", "HEAD") == PARENT,
        "origin_main_parent": git(root, "rev-parse", "origin/main") == PARENT,
        "branch_main": git(root, "branch", "--show-current") == "main",
        "no_staged_changes": staged == "",
        "overlay_scope_exact": changed_paths == EXPECTED_FILES,
        "selected_candidate_exact": cfg["execution_realization"]["selected_candidate"]
        == "P_CONSTR_RMIN_V2_HD_U",
        "scale_M_exact": cfg["execution_realization"]["scale_id"] == "M",
        "candidate_seed_exact": cfg["execution_realization"]["candidate_master_seed"] == 20261005,
        "h6_seed_exact": cfg["execution_realization"]["h6_master_seed"] == 20261004,
        "M_person_anchor": cfg["expected_M_materialization"]["persons"] == 100000,
        "M_household_anchor": cfg["expected_M_materialization"]["households"] == 54828,
        "M_strict_plan_anchor": cfg["expected_M_materialization"]["strict_households"] == 54026
        and cfg["expected_M_materialization"]["strict_persons"] == 93127,
        "M_h6_anchor": cfg["expected_M_materialization"]["six_plus_households"] == 802
        and cfg["expected_M_materialization"]["six_plus_persons"] == 6873,
        "M_fit_anchor": cfg["expected_M_materialization"]["target_fit_l1"] == 3172
        and cfg["expected_M_materialization"]["target_fit_max_abs"] == 40,
        "holdout_unacquired": hold["boundaries"]["holdout_1000A_1035_acquired"] is False,
        "holdout_unread": hold["boundaries"]["holdout_1000A_1035_values_read"] is False,
        "holdout_not_authorized": hold["holdout_authorization"]["authorized"] is False,
        "hold_thresh_001_still_open": hold["decision_threshold_status"]["blocker_id"]
        == "HOLD-THRESH-001",
        "negative_execution_template": auth["authorized"] is False
        and auth["mreal_execution_authorized"] is False,
        "negative_holdout_io": auth["holdout_value_io_authorized"] is False
        and auth["holdout_metric_evaluation_authorized"] is False,
        "cal_closed": cfg["boundaries"]["cal_reopened"] is False,
        "test_closed": cfg["boundaries"]["mid_test_reopened"] is False,
        "plr_closed": cfg["boundaries"]["spatial_plr_allocation"] is False,
        "f3_closed": cfg["boundaries"]["f3_modified"] is False,
        "G1_open": cfg["boundaries"]["G1"] == "OPEN",
        "G2_closed": cfg["boundaries"]["G2"] == "PASS_CLOSED_DO_NOT_REOPEN",
    }
    failed = [k for k, v in checks.items() if not v]
    out = {
        "phase": cfg["phase_id"],
        "parent": PARENT,
        "changed_paths": sorted(changed_paths),
        "checks": checks,
        "failed": failed,
        "controlled_state": {
            "holdout_1000A_1035_acquired": False,
            "holdout_1000A_1035_values_read": False,
            "positive_mreal_execution_authorization_issued": False,
            "M_realization_executed": False,
            "HOLD_MREAL_001": "OPEN_PENDING_COMMIT_BOUND_EXECUTION",
            "HOLD_THRESH_001": "OPEN",
            "G1": "OPEN",
            "G2": "PASS_CLOSED_DO_NOT_REOPEN",
        },
        "next_step_if_pass": (
            "COMMIT_AND_PUSH_MREAL_RUNNER_THEN_ISSUE_EXTERNAL_"
            "COMMIT_BOUND_MREAL_A1_AUTHORIZATION"
        ),
        "status": "PASS" if not failed else "FAIL",
    }
    print(json.dumps(out, indent=2, sort_keys=True))
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
