#!/usr/bin/env python3
from __future__ import annotations

import ast
import hashlib
import json
import subprocess
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
EXPECTED_PARENT = "cf4eff1544d2c3fc16d5d0039d6d2f2136a264a4"
GATE_CONFIG = ROOT / "configs/f1/f1_pconstr_cal01_precal_entry_gate_v1.yaml"
PREOPEN_CONFIG = ROOT / "configs/f1/f1_pconstr_cal01_preopen_v1.yaml"
AUTH_TEMPLATE = ROOT / "docs/F1_PCONSTR_CAL01_AUTHORIZATION_TEMPLATE_v1.json"
EVALUATOR = ROOT / "src/simfleet_edg/population/calibration_evaluation.py"

ALLOWED = {
    "configs/f1/f1_pconstr_cal01_precal_entry_gate_v1.yaml",
    "docs/F1_PCONSTR_CAL01_PRECAL_ENTRY_GATE_CHECKLIST_v1.csv",
    "docs/F1_PCONSTR_CAL01_PRECAL_ENTRY_GATE_OVERLAY_CHECKSUMS_v1.sha256",
    "docs/F1_PCONSTR_CAL01_PRECAL_ENTRY_GATE_OVERLAY_FILELIST_v1.txt",
    "docs/F1_PCONSTR_CAL01_PRECAL_ENTRY_GATE_v1.md",
    "scripts/verify_f1_pconstr_cal01_precal_entry_gate.py",
    "tests/test_f1_pconstr_cal01_precal_entry_gate.py",
}


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def changed_paths() -> set[str]:
    lines = subprocess.check_output(
        ["git", "status", "--porcelain"], cwd=ROOT, text=True
    ).splitlines()
    return {line[3:] for line in lines if len(line) >= 4}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def module_has_file_io(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    forbidden: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if isinstance(node.func, ast.Name) and node.func.id == "open":
            forbidden.append("open")
        if isinstance(node.func, ast.Attribute) and node.func.attr in {
            "read_csv",
            "read_parquet",
            "read_json",
            "read_excel",
            "to_csv",
            "to_parquet",
        }:
            forbidden.append(node.func.attr)
    return sorted(forbidden)


def tracked(path: str) -> bool:
    proc = subprocess.run(
        ["git", "ls-files", "--error-unmatch", path],
        cwd=ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    return proc.returncode == 0


def main() -> int:
    gate = yaml.safe_load(GATE_CONFIG.read_text(encoding="utf-8"))
    preopen = yaml.safe_load(PREOPEN_CONFIG.read_text(encoding="utf-8"))
    auth = json.loads(AUTH_TEMPLATE.read_text(encoding="utf-8"))
    changed = changed_paths()
    io_calls = module_has_file_io(EVALUATOR)

    frozen_hashes = gate["frozen_precal_assets"]
    frozen_hash_checks = {
        path: sha256(ROOT / path) == expected
        for path, expected in frozen_hashes.items()
    }
    frozen_tracked = {path: tracked(path) for path in frozen_hashes}

    b = preopen["cal_boundary"]
    policy = gate["entry_gate_policy"]
    checks = {
        "parent_head": git("rev-parse", "HEAD") == EXPECTED_PARENT,
        "branch_main": git("branch", "--show-current") == "main",
        "origin_main_parent": git("rev-parse", "origin/main") == EXPECTED_PARENT,
        "no_staged_changes": git("diff", "--cached", "--name-only") == "",
        "overlay_scope_exact": changed == ALLOWED,
        "frozen_assets_hash_exact": all(frozen_hash_checks.values()),
        "frozen_assets_tracked": all(frozen_tracked.values()),
        "evaluation_module_file_io_free": io_calls == [],
        "cal_rows_zero": b["calibration_rows_read"] == 0,
        "cal_not_authorized": b["calibration_authorized"] is False,
        "candidate_selection_none": b["candidate_selection"] == "NONE",
        "thresholds_not_frozen": b["g1_thresholds_v1"] == "NOT_FROZEN",
        "test_not_read": b["mid_test_read"] is False,
        "holdout_not_read": b["holdout_1000A_1035_read"] is False,
        "plr_not_allocated": b["spatial_plr_allocation"] is False,
        "f3_not_modified": b["f3_modified"] is False,
        "g1_open": b["G1"] == "OPEN",
        "g2_closed": b["G2"] == "PASS_CLOSED_DO_NOT_REOPEN",
        "authorization_template_false": auth["authorized"] is False,
        "authorization_commit_unbound": auth["required_precal_commit"] is None,
        "authorization_template_only": auth["authorization_status"]
        == "TEMPLATE_ONLY_NOT_AUTHORIZED",
        "candidate_universe_exact": gate["candidate_universe"]
        == ["P_TRS_V1_FINAL", "P_CONSTR_RMIN_V2_HD_U", "P_CONSTR_RMIN_V2_HD_W"],
        "bootstrap_1000": gate["threshold_protocol"]["bootstrap_replicates"] == 1000,
        "quantile_higher": gate["threshold_protocol"]["quantile_method"] == "higher",
        "seed_frozen": gate["threshold_protocol"]["master_seed"] == 20261005,
        "next_auth_binds_to_gate_commit": policy[
            "next_authorization_must_bind_to_entry_gate_commit"
        ]
        is True,
        "no_cal_reader_allowed": policy["cal_reader_allowed_in_this_subphase"] is False,
        "no_numeric_thresholds": policy["numeric_thresholds_allowed_in_this_subphase"]
        is False,
        "no_candidate_selection": policy["candidate_selection_allowed_in_this_subphase"]
        is False,
    }
    failed = [key for key, value in checks.items() if not value]

    payload = {
        "phase": "F1-P_CONSTR-CAL-01 PRE-CAL ENTRY GATE",
        "parent": EXPECTED_PARENT,
        "changed_paths": sorted(changed),
        "frozen_asset_hash_checks": frozen_hash_checks,
        "frozen_asset_tracked_checks": frozen_tracked,
        "forbidden_file_io_calls": io_calls,
        "checks": checks,
        "failed": failed,
        "status": "PASS" if not failed else "FAIL",
        "next_step_if_pass": "COMMIT_AND_PUSH_ENTRY_GATE_THEN_BUILD_COMMIT_BOUND_AUTHORIZATION",
        "controlled_lineage_boundary": gate["controlled_lineage_boundary"],
        "traceability_caveat": gate["traceability_caveat"],
    }
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
