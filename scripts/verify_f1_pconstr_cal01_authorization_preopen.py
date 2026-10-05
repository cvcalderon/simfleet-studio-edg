#!/usr/bin/env python3
from __future__ import annotations

import ast
import hashlib
import json
import subprocess
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
EXPECTED_PARENT = "83df51a035d21621b9c5b8de04b6f03ea1a78174"
NEW_FILES = {
    "configs/f1/f1_pconstr_cal01_authorization_v1.yaml",
    "docs/F1_PCONSTR_CAL01_AUTHORIZATION_v1.json",
    "docs/F1_PCONSTR_CAL01_AUTHORIZATION_PREOPEN_v1.md",
    "docs/F1_PCONSTR_CAL01_AUTHORIZATION_OVERLAY_CHECKSUMS_v1.sha256",
    "docs/F1_PCONSTR_CAL01_AUTHORIZATION_OVERLAY_FILELIST_v1.txt",
    "scripts/verify_f1_pconstr_cal01_authorization_preopen.py",
    "tests/test_f1_pconstr_cal01_authorization_preopen.py",
}
FROZEN_TEMPLATE = ROOT / "docs/F1_PCONSTR_CAL01_AUTHORIZATION_TEMPLATE_v1.json"
ENTRY_GATE_CONFIG = ROOT / "configs/f1/f1_pconstr_cal01_precal_entry_gate_v1.yaml"
AUTH = ROOT / "docs/F1_PCONSTR_CAL01_AUTHORIZATION_v1.json"
CONFIG = ROOT / "configs/f1/f1_pconstr_cal01_authorization_v1.yaml"

def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()

def changed_paths() -> set[str]:
    out = subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT, text=True)
    return {line[3:] for line in out.splitlines() if line.strip()}

def no_forbidden_io(path: Path) -> tuple[bool, list[str]]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    bad=[]
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            f=node.func
            name = f.attr if isinstance(f, ast.Attribute) else (f.id if isinstance(f, ast.Name) else "")
            if name in {"read_csv","read_parquet","read_excel","open"}:
                bad.append(name)
    return not bad, bad

def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()

def main() -> int:
    auth=json.loads(AUTH.read_text(encoding="utf-8"))
    cfg=yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    template=json.loads(FROZEN_TEMPLATE.read_text(encoding="utf-8"))
    gate=yaml.safe_load(ENTRY_GATE_CONFIG.read_text(encoding="utf-8"))
    changed=changed_paths()
    io_ok,bad=no_forbidden_io(Path(__file__))
    checks={
      "branch_main": git("branch","--show-current")=="main",
      "parent_head": git("rev-parse","HEAD")==EXPECTED_PARENT,
      "origin_main_parent": git("rev-parse","origin/main")==EXPECTED_PARENT,
      "no_staged_changes": git("diff","--cached","--name-only")=="",
      "overlay_scope_exact": changed==NEW_FILES,
      "template_still_false": template.get("authorized") is False,
      "template_still_unbound": template.get("required_precal_commit") is None,
      "entry_gate_requires_binding": gate["entry_gate_policy"]["next_authorization_must_bind_to_entry_gate_commit"] is True,
      "authorization_true": auth.get("authorized") is True,
      "authorization_bound_exact": auth.get("required_precal_commit")==EXPECTED_PARENT,
      "authorization_partition_cal_only": auth.get("allowed_partition")=="CALIBRATION_ONLY",
      "cal_rows_zero_at_authorization": auth.get("calibration_rows_read_at_authorization")==0,
      "candidate_selection_none": auth.get("candidate_selection_before_authorized_run")=="NONE",
      "thresholds_not_frozen": auth.get("g1_thresholds_before_authorized_run")=="NOT_FROZEN",
      "no_cal_reader_in_subphase": auth.get("cal_reader_present_in_authorization_subphase") is False,
      "config_matches_auth": cfg["controlled_authorization"]["required_precal_commit"]==EXPECTED_PARENT and cfg["controlled_authorization"]["authorized"] is True,
      "test_forbidden": "MiD TEST rows" in auth.get("forbidden_inputs",[]),
      "holdout_forbidden": "1000A-1035" in auth.get("forbidden_inputs",[]),
      "plr_forbidden": "PLR target allocation inputs" in auth.get("forbidden_inputs",[]),
      "f3_forbidden": "F3 held-out TEST artifacts" in auth.get("forbidden_inputs",[]),
      "verifier_file_io_free": io_ok,
    }
    failed=[k for k,v in checks.items() if not v]
    result={
      "phase":"F1-P_CONSTR-CAL-01 CAL AUTHORIZATION PREOPEN",
      "parent":EXPECTED_PARENT,
      "changed_paths":sorted(changed),
      "checks":checks,
      "failed":failed,
      "forbidden_file_io_calls":bad,
      "controlled_state":{
        "calibration_authorized": True,
        "calibration_rows_read": 0,
        "candidate_selection":"NONE",
        "g1_thresholds_v1":"NOT_FROZEN",
        "mid_test_read":False,
        "holdout_1000A_1035_read":False,
        "spatial_plr_allocation":False,
        "f3_modified":False,
        "G1":"OPEN",
        "G2":"PASS_CLOSED_DO_NOT_REOPEN",
      },
      "next_step_if_pass":"COMMIT_AND_PUSH_AUTHORIZATION_THEN_BUILD_BOUND_CAL_RUNNER",
      "status":"PASS" if not failed else "FAIL",
    }
    print(json.dumps(result,indent=2,sort_keys=True))
    return 0 if not failed else 1

if __name__ == "__main__":
    raise SystemExit(main())
