from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

import pandas as pd
import yaml

ROOT = Path.cwd()
PARENT = "3a6b0eb3e3ef4ab9311383a418c88d9e9ef20ada"
FILELIST = ROOT / "docs/F3_4A_OVERLAY_FILELIST_v1.txt"
CHECKSUMS = ROOT / "docs/F3_4A_OVERLAY_CHECKSUMS_v1.sha256"
CONFIG = ROOT / "configs/f3/f3_4a_controlled_cal_execution_contract_v1.yaml"
PLAN = ROOT / "docs/F3_4A_CANDIDATE_EXECUTION_PLAN_v1.csv"
INPUTS = ROOT / "docs/F3_4A_CAL_INPUT_MANIFEST_v1.csv"


def run(*args: str) -> str:
    return subprocess.check_output(args, cwd=ROOT, text=True).strip()


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate_sha_manifest(path: Path) -> bool:
    ok = True
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line:
            continue
        digest, rel = line.split("  ", 1)
        target = ROOT / rel
        ok &= target.is_file() and sha256(target) == digest
    return bool(ok)


def main() -> None:
    cfg = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    checks: dict[str, bool] = {}
    checks["head_exact_parent"] = run("git", "rev-parse", "HEAD") == PARENT
    checks["branch_main"] = run("git", "branch", "--show-current") == "main"
    ahead, behind = run("git", "rev-list", "--left-right", "--count", "HEAD...origin/main").split()
    checks["ahead_zero"] = ahead == "0"
    checks["behind_zero"] = behind == "0"
    checks["no_staged_changes"] = run("git", "diff", "--cached", "--name-only") == ""

    expected = {line for line in FILELIST.read_text(encoding="utf-8").splitlines() if line}
    changed = {line[3:] for line in run("git", "status", "--porcelain").splitlines() if line}
    checks["overlay_scope_exact"] = changed == expected
    checks["overlay_checksums_exact"] = validate_sha_manifest(CHECKSUMS)

    witness_ok = True
    for spec in cfg["frozen_witnesses"].values():
        p = ROOT / spec["path"]
        witness_ok &= p.is_file() and sha256(p) == spec["sha256"]
    checks["frozen_witnesses_exact"] = bool(witness_ok)

    registry_path = ROOT / cfg["candidate_registry"]["path"]
    registry = pd.read_csv(registry_path, dtype=str)
    counts = registry.groupby("component").size().to_dict()
    checks["candidate_registry_exact"] = (
        sha256(registry_path) == cfg["candidate_registry"]["sha256"]
        and len(registry) == 31
        and counts == cfg["candidate_registry"]["counts"]
        and set(registry["train_state"]) == {cfg["candidate_registry"]["required_train_state"]}
    )

    plan = pd.read_csv(PLAN, dtype=str)
    checks["candidate_plan_exact"] = (
        len(plan) == 31
        and set(plan["artifact_id"]) == set(registry["artifact_id"])
        and plan.groupby("component").size().to_dict() == cfg["candidate_registry"]["counts"]
    )

    inputs = pd.read_csv(INPUTS, dtype={"expected_rows": int})
    cal_root = ROOT / cfg["cal_input"]["root"]
    checks["cal_paths_declared_only"] = set(inputs["filename"]) == set(cfg["cal_input"]["allowed_files"])
    checks["cal_files_exist_without_reading"] = all((cal_root / name).is_file() for name in cfg["cal_input"]["allowed_files"])
    checks["test_path_not_present"] = not (ROOT / cfg["cal_input"]["test_path_forbidden"]).exists()

    checks["one_component_at_a_time"] = (
        cfg["run_governance"]["granularity"] == "ONE_COMPONENT_AT_A_TIME"
        and cfg["run_governance"]["stop_after_each_component"] is True
        and cfg["run_governance"]["main_review_required_before_next_component"] is True
        and cfg["run_governance"]["first_component_run"] == "DG_PARTICIPATION"
    )
    checks["first_run_participation_only"] = (
        cfg["first_controlled_run"]["component"] == "DG_PARTICIPATION"
        and cfg["first_controlled_run"]["candidate_artifacts"] == 8
        and cfg["first_controlled_run"]["downstream_components_authorized_in_same_run"] is False
    )
    checks["test_still_sealed"] = (
        cfg["boundary_at_f3_4a"]["test_partition"] == "SEALED"
        and cfg["boundary_at_f3_4a"]["test_rows_read"] == 0
        and cfg["first_controlled_run"]["test_authorized"] is False
    )
    checks["cal_unread_in_contract_freeze"] = (
        cfg["boundary_at_f3_4a"]["cal_rows_read"] == 0
        and cfg["boundary_at_f3_4a"]["candidate_selection"] == "NONE"
    )
    checks["frozen_protocol"] = (
        cfg["cal_session"]["master_seed"] == 20260926
        and cfg["cal_session"]["stochastic_replicates"] == 32
        and cfg["cal_session"]["household_bootstrap_replicates"] == 1000
        and float(cfg["cal_session"]["confidence_level"]) == 0.95
        and cfg["selection_mechanics"]["type"] == "LEXICOGRAPHIC_NO_COMPOSITE_SCORE"
    )
    checks["part_b_post_selection_calibration"] = (
        cfg["part_b_calibration"]["folds"] == 5
        and cfg["part_b_calibration"]["timing"] == "ONLY_AFTER_PART_B_GRID_AND_COMPONENT_FAMILY_GRID_SELECTION"
        and cfg["part_b_calibration"]["cannot_rescue_nonselected_part_b"] is True
    )

    failed = [k for k,v in checks.items() if not bool(v)]
    print(json.dumps({
        "status": "PASS" if not failed else "FAIL",
        "phase": "F3.4a",
        "contract_freeze": "PASS" if not failed else "FAIL",
        "candidate_artifacts": len(plan),
        "cal_rows_read": 0,
        "test_rows_read": 0,
        "candidate_selection": "NONE",
        "first_future_controlled_cal_component": "DG_PARTICIPATION",
        "cal_read_performed_by_verifier": False,
        "test_open_authorized": False,
        "formal_g2": "NOT_EVALUATED",
        "checks": {k: bool(v) for k,v in checks.items()},
        "failed": failed,
    }, indent=2, sort_keys=True))
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
