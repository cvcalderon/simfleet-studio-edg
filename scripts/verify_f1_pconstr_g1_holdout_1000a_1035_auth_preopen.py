#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
EXPECTED_PARENT = "f6b53d605f4e2ae73a1ad873838eb8cd8d8aca64"
EXPECTED_THRESHOLD = "0.0815667541845037"
EXPECTED_MREAL_SHA = "00b440d58b2c4f7f5484e8260a43f1fb9f2ce69c0b5d5c23a6272aa3b2afa505"
EXPECTED_METRIC_PREOPEN_COMMIT = "faa8a024498f672f1b4e34dbd54219afef020a1a"

CFG = ROOT / "configs/f1/f1_pconstr_g1_holdout_1000a_1035_auth_preopen_v1.yaml"
AUTH_TEMPLATE = ROOT / "docs/F1_PCONSTR_G1_HOLDOUT_1000A_1035_EXECUTION_AUTHORIZATION_TEMPLATE_A1.json"
OLD_HOLDOUT_CHECKSUMS = ROOT / "docs/F1_PCONSTR_G1_HOLDOUT_1000A_1035_OVERLAY_CHECKSUMS_v1.sha256"
MREAL_CHECKSUMS = ROOT / "docs/F1_PCONSTR_G1_HOLD_MREAL01_FREEZE_OVERLAY_CHECKSUMS_v1.sha256"
THRESH_CHECKSUMS = ROOT / "docs/F1_PCONSTR_G1_HOLD_THRESH01_OVERLAY_CHECKSUMS_v1.sha256"
FILELIST = ROOT / "docs/F1_PCONSTR_G1_HOLDOUT_1000A_1035_AUTH_PREOPEN_OVERLAY_FILELIST_v1.txt"


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def verify_sha_manifest(path: Path) -> bool:
    if not path.is_file():
        return False
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line:
            continue
        try:
            expected, rel = line.split(maxsplit=1)
        except ValueError:
            return False
        target = ROOT / rel.strip()
        if not target.is_file():
            return False
        actual = hashlib.sha256(target.read_bytes()).hexdigest()
        if actual != expected:
            return False
    return True


def is_ancestor(commit: str, descendant: str) -> bool:
    result = subprocess.run(
        ["git", "merge-base", "--is-ancestor", commit, descendant],
        cwd=ROOT,
        check=False,
    )
    return result.returncode == 0


def main() -> int:
    cfg = yaml.safe_load(CFG.read_text(encoding="utf-8"))
    auth = json.loads(AUTH_TEMPLATE.read_text(encoding="utf-8"))

    head = git("rev-parse", "HEAD")
    origin = git("rev-parse", "origin/main")
    branch = git("branch", "--show-current")
    status_lines = [
        line
        for line in git("status", "--porcelain", "--untracked-files=all").splitlines()
        if line
    ]
    staged_clean = git("diff", "--cached", "--name-only") == ""
    tracked_diff_clean = git("diff", "--name-only") == ""
    expected_overlay_paths = set(FILELIST.read_text(encoding="utf-8").splitlines())
    untracked_paths = {
        line[3:]
        for line in status_lines
        if line.startswith("?? ")
    }
    only_untracked = all(line.startswith("?? ") for line in status_lines)

    lineage = cfg["frozen_lineage"]
    boundaries = cfg["boundaries"]
    metrics = cfg["metrics"]

    checks = {
        "branch_main": branch == "main",
        "head_exact_parent": head == EXPECTED_PARENT,
        "origin_exact_parent": origin == EXPECTED_PARENT,
        "overlay_scope_exact": only_untracked and untracked_paths == expected_overlay_paths,
        "no_tracked_worktree_changes": tracked_diff_clean,
        "no_staged_changes": staged_clean,
        "metric_preopen_is_ancestor": is_ancestor(EXPECTED_METRIC_PREOPEN_COMMIT, head),
        "old_holdout_preopen_bytes_frozen": verify_sha_manifest(OLD_HOLDOUT_CHECKSUMS),
        "mreal_freeze_bytes_frozen": verify_sha_manifest(MREAL_CHECKSUMS),
        "threshold_freeze_bytes_frozen": verify_sha_manifest(THRESH_CHECKSUMS),
        "candidate_exact": lineage["selected_candidate"] == "P_CONSTR_RMIN_V2_HD_U",
        "mreal_frozen": lineage["mreal_status"] == "RESOLVED_FROZEN",
        "mreal_sha_exact": lineage["mreal_runbundle_sha256"] == EXPECTED_MREAL_SHA,
        "threshold_frozen": lineage["threshold_status"] == "RESOLVED_FROZEN",
        "threshold_rule_exact": lineage["threshold_rule"] == "MAX_FROZEN_CAL_TVD_MATERIALITY_TAU_V1",
        "threshold_exact": str(lineage["threshold_value"]) == EXPECTED_THRESHOLD,
        "candidate_seed_exact": lineage["candidate_master_seed"] == 20261005,
        "h6_seed_exact": lineage["h6_master_seed"] == 20261004,
        "holdout_randomness_none": lineage["holdout_metric_randomness"] == "NONE",
        "berlin_tvd_decision": metrics["G1-HOLD-SEN-BERLIN-TVD"]["role"] == "DECISION",
        "bez_wtvd_decision": metrics["G1-HOLD-SEN-BEZ-WTVD"]["role"] == "DECISION",
        "bez_max_report_only": metrics["G1-HOLD-SEN-BEZ-MAX"]["role"] == "REPORT_ONLY",
        "both_metrics_required": metrics["pass_requires_all_decision_metrics"] is True,
        "no_composite_score": metrics["no_composite_score"] is True,
        "mreal_boundary_frozen": boundaries["HOLD_MREAL_001"] == "RESOLVED_FROZEN",
        "threshold_boundary_frozen": boundaries["HOLD_THRESH_001"] == "RESOLVED_FROZEN",
        "holdout_unacquired": boundaries["holdout_1000A_1035_acquired"] is False,
        "holdout_unread": boundaries["holdout_1000A_1035_values_read"] is False,
        "holdout_not_authorized": boundaries["holdout_1000A_1035_authorized"] is False,
        "holdout_not_evaluated": boundaries["holdout_metric_evaluation"] is False,
        "cal_closed": boundaries["CAL"] == "CLOSED_DO_NOT_REOPEN",
        "test_closed": boundaries["MiD_TEST"] == "CONSUMED_BY_G2_DO_NOT_REOPEN",
        "plr_closed": boundaries["spatial_plr_allocation"] is False,
        "f3_closed": boundaries["f3_modified"] is False,
        "g1_open": boundaries["G1"] == "OPEN",
        "g2_closed": boundaries["G2"] == "PASS_CLOSED_DO_NOT_REOPEN",
        "no_holdout_data_path_in_repo": not any(
            ("1000a_1035" in path.lower() or "1000a-1035" in path.lower())
            and (path.startswith("data/") or path.startswith("artifacts/"))
            for path in git("ls-files", "--cached", "--others", "--exclude-standard").splitlines()
        ),
        "authorization_template_negative": auth["authorized"] is False,
        "authorization_status_negative": auth["status"] == "TEMPLATE_NEGATIVE_NOT_AUTHORIZED",
        "authorization_commit_placeholder": auth["required_authoritative_commit"] == "__AUTH_PREOPEN_COMMIT__",
        "authorization_acquire_false": auth["authorized_actions"]["acquire_1000A_1035"] is False,
        "authorization_read_false": auth["authorized_actions"]["read_1000A_1035_values"] is False,
        "authorization_eval_false": auth["authorized_actions"]["evaluate_frozen_senior_metrics"] is False,
    }

    failed = [key for key, value in checks.items() if not value]
    out = {
        "phase": "F1-P-CONSTR-G1-HOLDOUT-1000A-1035 AUTH-PREOPEN",
        "parent": EXPECTED_PARENT,
        "selected_candidate": lineage["selected_candidate"],
        "threshold": EXPECTED_THRESHOLD,
        "checks": checks,
        "failed": failed,
        "controlled_state": {
            "G1": boundaries["G1"],
            "G2": boundaries["G2"],
            "HOLD_MREAL_001": boundaries["HOLD_MREAL_001"],
            "HOLD_THRESH_001": boundaries["HOLD_THRESH_001"],
            "holdout_1000A_1035_acquired": boundaries["holdout_1000A_1035_acquired"],
            "holdout_1000A_1035_values_read": boundaries["holdout_1000A_1035_values_read"],
            "holdout_1000A_1035_authorized": boundaries["holdout_1000A_1035_authorized"],
        },
        "next_step_if_pass": "COMMIT_AND_PUSH_AUTH_PREOPEN_THEN_ISSUE_EXTERNAL_COMMIT_BOUND_AUTHORIZATION_A1",
        "holdout_value_io_authorized": False,
        "status": "PASS" if not failed else "FAIL",
    }
    print(json.dumps(out, indent=2, sort_keys=True))
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
