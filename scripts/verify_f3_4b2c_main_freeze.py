#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import subprocess
from pathlib import Path

EXPECTED_PARENT = "d3ad3ba5881cc5629db4b64782441199c6f69df8"
EXPECTED_SELECTED = "DG_PARTICIPATION::PART_A::PA1"
EXPECTED_OVERLAY_FILES = {
    "configs/f3/f3_4b2c_participation_main_freeze_v1.yaml",
    "docs/F3_4B2C_EXECUTION_INSTRUCTIONS_v1.md",
    "docs/F3_4B2C_MAIN_SELECTION_FREEZE_v1.md",
    "docs/F3_4B2C_OVERLAY_CHECKSUMS_v1.sha256",
    "docs/F3_4B2C_OVERLAY_FILELIST_v1.txt",
    "docs/F3_4B2C_RUNBUNDLE_WITNESSES_v1.sha256",
    "docs/MAIN_UPDATE_F3_4B2C_v1.md",
    "scripts/verify_f3_4b2c_main_freeze.py",
    "tests/test_f3_4b2c_main_freeze.py",
}
EXPECTED_WITNESSES = {
    "checksums.sha256":"0f3e934fedef3297ae42d56c62b9e3002e512ad0976c4a3e7a5a3545b24ffff9",
    "run_manifest.json":"77c1ff1e6c6b8e2c144c407dd89292ded28bf92783d86d138de258d868f61d2a",
    "evidence_manifest.json":"b3d4a74153b84145d627b9bad8997859825cc5018fe81843b3842e3af94faa73",
    "execution_authorization_snapshot.json":"13bbbfbe06afbb8369f0f07c6134b54f963ab5c88527c2da2e020ed5fe69f9f7",
    "input_hash_validation.csv":"eed56fab89cb8322a15d5b571c6cc5b2334267dd39f29edbadd4b928b140d338",
    "primary_metrics.csv":"2ab0cc324a10a8a5a3d328948d8896cb388e230fd8dadca8c2390829655587c5",
    "grid_selection.csv":"8f16f574bbaef8ba2d6a3038b1d9f941cde5880fd4e4ab49710d33edd0ac3a0f",
    "promotion_decisions.csv":"31a7725b78e1611aec411d650e5d084f4bb827664429d56135fa22e621866503",
    "bootstrap_intervals.csv":"918acf8687bfa912ff27ab11ff806e3ae5b1e056f0560400952041d3aa482fc4",
    "guardrails.csv":"009a2fc1879633bbaeb1f3f268e66eea8d14a699826e4a0431a88500dce37e8e",
    "selected_component_artifact.json":"8c29c1f96fecde7cf02bbfb5bb31ea9e5cf51be36d7b353795d989eb4990c500",
    "part_b_calibration_decision.json":"8999eba3992a936f1dc6ceb52767c40105f5dc4bed2fc890778a3d8fa967d017",
}

def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()

def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], text=True).strip()

def git_ok(*args: str) -> bool:
    return subprocess.run(["git", *args], check=False).returncode == 0

def load_csv(path: Path):
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-dir", required=True)
    ns = ap.parse_args()
    run = Path(ns.run_dir)

    checks = {}
    checks["head_exact_parent"] = git("rev-parse", "HEAD") == EXPECTED_PARENT
    checks["branch_main"] = git("branch", "--show-current") == "main"
    checks["ahead_zero"] = git("rev-list", "--count", "origin/main..HEAD") == "0"
    checks["behind_zero"] = git("rev-list", "--count", "HEAD..origin/main") == "0"

    # PRE-COMMIT semantics: the overlay itself is intentionally untracked.
    # What must be clean is the tracked/staged state, and the untracked scope
    # must be exactly the frozen F3.4b-2c overlay.
    checks["no_tracked_worktree_changes"] = git_ok("diff", "--quiet")
    checks["no_staged_changes"] = git_ok("diff", "--cached", "--quiet")
    untracked = {
        line for line in git("ls-files", "--others", "--exclude-standard").splitlines()
        if line
    }
    checks["overlay_scope_exact"] = untracked == EXPECTED_OVERLAY_FILES

    for name, expected in EXPECTED_WITNESSES.items():
        p = run / name
        checks[f"witness_{name}"] = p.exists() and sha256(p) == expected

    manifest = json.loads((run / "run_manifest.json").read_text(encoding="utf-8"))
    selected = json.loads((run / "selected_component_artifact.json").read_text(encoding="utf-8"))
    cal = json.loads((run / "part_b_calibration_decision.json").read_text(encoding="utf-8"))

    checks["run_pass"] = manifest.get("status") == "PASS"
    checks["component_exact"] = manifest.get("component") == "DG_PARTICIPATION"
    checks["cal_rows_929"] = manifest.get("cal_rows_read_total_physical") == 929
    checks["eval_rows_460"] = manifest.get("cal_evaluation_rows") == 460
    checks["test_rows_zero"] = manifest.get("test_rows_read") == 0
    checks["test_sealed"] = manifest.get("test_open_authorized") is False
    checks["g2_not_evaluated"] = manifest.get("formal_g2") == "NOT_EVALUATED"
    checks["proposal_exact"] = manifest.get("proposed_selected_artifact_id") == EXPECTED_SELECTED
    checks["proposal_not_frozen_in_run"] = (
        selected.get("status") == "PROPOSED_BY_FROZEN_CAL_RULES_NOT_MAIN_FROZEN"
    )
    checks["calibrator_not_retained"] = cal.get("retained") is False

    pm = {r["artifact_id"]: r for r in load_csv(run / "primary_metrics.csv")}
    grid = load_csv(run / "grid_selection.csv")
    promos = load_csv(run / "promotion_decisions.csv")
    guards = load_csv(run / "guardrails.csv")

    checks["pa1_primary_exact"] = (
        abs(float(pm[EXPECTED_SELECTED]["value"]) - 0.3388982435885032) < 1e-15
    )
    checks["pa1_family_winner"] = any(
        r["artifact_id"] == EXPECTED_SELECTED and r["selected_within_family"] == "True"
        for r in grid
    )
    checks["pb1_family_winner"] = any(
        r["artifact_id"] == "DG_PARTICIPATION::PART_B::PB1"
        and r["selected_within_family"] == "True"
        for r in grid
    )
    ref_a = next(r for r in promos if r["stage"] == "REF_TO_A")
    a_b = next(r for r in promos if r["stage"] == "INCUMBENT_TO_B")
    checks["ref_to_a_promoted"] = ref_a["promoted"] == "True"
    checks["a_to_b_not_promoted"] = a_b["promoted"] == "False"
    checks["all_guardrails_pass"] = all(
        r["guardrails_pass"] == "True" for r in guards
    )

    failed = [k for k, v in checks.items() if not v]
    out = {
        "phase": "F3.4b-2c",
        "status": "PASS" if not failed else "FAIL",
        "main_freeze_gate": "PASS" if not failed else "FAIL",
        "selected_artifact_id": EXPECTED_SELECTED if not failed else None,
        "selection_state_if_committed": "MAIN_FROZEN" if not failed else "NOT_FROZEN",
        "test_open_authorized": False,
        "formal_g2": "NOT_EVALUATED",
        "next_component_authorized": False,
        "checks": checks,
        "failed": failed,
    }
    print(json.dumps(out, indent=2, sort_keys=True))
    return 0 if not failed else 1

if __name__ == "__main__":
    raise SystemExit(main())
