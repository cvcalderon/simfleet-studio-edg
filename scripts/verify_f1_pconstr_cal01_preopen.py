#!/usr/bin/env python3
from __future__ import annotations

import ast
import json
import subprocess
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
EXPECTED_PARENT = "45c6f10f4168e26fd6929b245adf505a3b2f1584"
ALLOWED = {
    "configs/f1/f1_pconstr_cal01_preopen_v1.yaml",
    "docs/F1_PCONSTR_CAL01_AUTHORIZATION_TEMPLATE_v1.json",
    "docs/F1_PCONSTR_CAL01_EVALUATION_CONTRACT_v1.md",
    "docs/F1_PCONSTR_CAL01_OVERLAY_CHECKSUMS_v1.sha256",
    "docs/F1_PCONSTR_CAL01_OVERLAY_FILELIST_v1.txt",
    "docs/F1_PCONSTR_CAL01_PREOPEN_v1.md",
    "docs/F1_PCONSTR_CAL01_THRESHOLD_RULE_v1.md",
    "scripts/verify_f1_pconstr_cal01_preopen.py",
    "src/simfleet_edg/population/calibration_evaluation.py",
    "tests/test_f1_pconstr_cal01_config.py",
    "tests/test_f1_pconstr_calibration_evaluation.py",
}


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def changed_paths() -> set[str]:
    out = subprocess.check_output(
        ["git", "status", "--porcelain"], cwd=ROOT, text=True
    ).splitlines()
    return {line[3:] for line in out if len(line) >= 4}


def module_has_file_io(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    forbidden: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name) and node.func.id in {"open"}:
                forbidden.append(node.func.id)
            if isinstance(node.func, ast.Attribute) and node.func.attr in {
                "read_csv", "read_parquet", "read_json", "read_excel", "to_csv", "to_parquet"
            }:
                forbidden.append(node.func.attr)
    return sorted(forbidden)


def main() -> int:
    cfg = yaml.safe_load((ROOT / "configs/f1/f1_pconstr_cal01_preopen_v1.yaml").read_text())
    auth = json.loads((ROOT / "docs/F1_PCONSTR_CAL01_AUTHORIZATION_TEMPLATE_v1.json").read_text())
    changed = changed_paths()
    module = ROOT / "src/simfleet_edg/population/calibration_evaluation.py"
    io_calls = module_has_file_io(module)
    checks = {
        "parent_head": git("rev-parse", "HEAD") == EXPECTED_PARENT,
        "branch_main": git("branch", "--show-current") == "main",
        "origin_main_parent": git("rev-parse", "origin/main") == EXPECTED_PARENT,
        "no_staged_changes": git("diff", "--cached", "--name-only") == "",
        "overlay_scope_exact": changed == ALLOWED,
        "evaluation_module_file_io_free": io_calls == [],
        "cal_rows_zero": cfg["cal_boundary"]["calibration_rows_read"] == 0,
        "cal_not_authorized": cfg["cal_boundary"]["calibration_authorized"] is False,
        "candidate_selection_none": cfg["cal_boundary"]["candidate_selection"] == "NONE",
        "thresholds_not_frozen": cfg["cal_boundary"]["g1_thresholds_v1"] == "NOT_FROZEN",
        "test_not_read": cfg["cal_boundary"]["mid_test_read"] is False,
        "holdout_not_read": cfg["cal_boundary"]["holdout_1000A_1035_read"] is False,
        "plr_not_allocated": cfg["cal_boundary"]["spatial_plr_allocation"] is False,
        "f3_not_modified": cfg["cal_boundary"]["f3_modified"] is False,
        "g1_open": cfg["cal_boundary"]["G1"] == "OPEN",
        "g2_closed": cfg["cal_boundary"]["G2"] == "PASS_CLOSED_DO_NOT_REOPEN",
        "authorization_template_false": auth["authorized"] is False,
        "authorization_commit_unbound": auth["required_precal_commit"] is None,
        "bootstrap_1000": cfg["threshold_derivation"]["bootstrap_replicates"] == 1000,
        "quantile_higher": cfg["threshold_derivation"]["quantile_method"] == "higher",
        "no_composite_score": cfg["selection_rule"]["no_composite_score"] is True,
    }
    failed = [k for k, v in checks.items() if not v]
    print(json.dumps({
        "phase": "F1-P_CONSTR-CAL-01 PREOPEN",
        "parent": EXPECTED_PARENT,
        "changed_paths": sorted(changed),
        "forbidden_file_io_calls": io_calls,
        "checks": checks,
        "failed": failed,
        "status": "PASS" if not failed else "FAIL",
        "boundaries": cfg["cal_boundary"],
    }, indent=2, sort_keys=True))
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
