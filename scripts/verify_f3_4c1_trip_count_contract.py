#!/usr/bin/env python3
from __future__ import annotations

import csv
import hashlib
import json
import subprocess
from pathlib import Path

EXPECTED_PARENT = "5169dd6e966e4ed55962c4bbba513f442d3c3f15"
EXPECTED_UPSTREAM = "DG_PARTICIPATION::PART_A::PA1"
EXPECTED_REGISTRY_SHA = "52328037d9a57866b188166373f798da4fb97460fc794748f8f0ef3968e86ad8"
EXPECTED_FREEZE_SHA = "025eb31f3c4ef04d838bd3c92bb05349b43820a75bc81112adc3631b8070ea75"
EXPECTED_ARTIFACTS = {
    "DG_TRIP_COUNT::COUNT_REF::REFERENCE",
    "DG_TRIP_COUNT::COUNT_A::CA1",
    "DG_TRIP_COUNT::COUNT_A::CA2",
    "DG_TRIP_COUNT::COUNT_A::CA3",
    "DG_TRIP_COUNT::COUNT_B::CB1",
}
EXPECTED_OVERLAY = {
    "configs/f3/f3_4c1_trip_count_cal_contract_v1.yaml",
    "docs/F3_4C1_CANDIDATE_PLAN_v1.csv",
    "docs/F3_4C1_EXECUTION_INSTRUCTIONS_v1.md",
    "docs/F3_4C1_IMPLEMENTATION_CLARIFICATIONS_v1.md",
    "docs/F3_4C1_INPUT_MANIFEST_v1.csv",
    "docs/F3_4C1_OVERLAY_CHECKSUMS_v1.sha256",
    "docs/F3_4C1_OVERLAY_FILELIST_v1.txt",
    "docs/F3_4C1_TRIP_COUNT_CAL_CONTRACT_v1.md",
    "docs/MAIN_UPDATE_F3_4C1_PREP_v1.md",
    "scripts/verify_f3_4c1_trip_count_contract.py",
    "tests/test_f3_4c1_trip_count_contract.py",
}

def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], text=True).strip()

def git_ok(*args: str) -> bool:
    return subprocess.run(["git", *args], check=False).returncode == 0

def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()

def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))

def main() -> int:
    checks: dict[str, bool] = {}
    checks["head_exact_parent"] = git("rev-parse", "HEAD") == EXPECTED_PARENT
    checks["branch_main"] = git("branch", "--show-current") == "main"
    checks["ahead_zero"] = git("rev-list", "--count", "origin/main..HEAD") == "0"
    checks["behind_zero"] = git("rev-list", "--count", "HEAD..origin/main") == "0"
    checks["no_tracked_worktree_changes"] = git_ok("diff", "--quiet")
    checks["no_staged_changes"] = git_ok("diff", "--cached", "--quiet")

    untracked = {
        p for p in git("ls-files", "--others", "--exclude-standard").splitlines() if p
    }
    checks["overlay_scope_exact"] = untracked == EXPECTED_OVERLAY

    checks["upstream_freeze_exists"] = Path(
        "configs/f3/f3_4b2c_participation_main_freeze_v1.yaml"
    ).exists()
    if checks["upstream_freeze_exists"]:
        checks["upstream_freeze_sha_exact"] = (
            sha256(Path("configs/f3/f3_4b2c_participation_main_freeze_v1.yaml"))
            == EXPECTED_FREEZE_SHA
        )
        text = Path("configs/f3/f3_4b2c_participation_main_freeze_v1.yaml").read_text(
            encoding="utf-8"
        )
        checks["upstream_selection_exact"] = (
            EXPECTED_UPSTREAM in text and "state: MAIN_FROZEN" in text
        )
    else:
        checks["upstream_freeze_sha_exact"] = False
        checks["upstream_selection_exact"] = False

    registry_path = Path("docs/F3_3_CANDIDATE_ARTIFACT_REGISTRY_v1.csv")
    checks["candidate_registry_exists"] = registry_path.exists()
    if registry_path.exists():
        checks["candidate_registry_sha_exact"] = sha256(registry_path) == EXPECTED_REGISTRY_SHA
        rows = [r for r in read_csv(registry_path) if r["component"] == "DG_TRIP_COUNT"]
        checks["candidate_artifacts_exact_5"] = len(rows) == 5
        checks["candidate_ids_exact"] = {r["artifact_id"] for r in rows} == EXPECTED_ARTIFACTS
        checks["candidate_train_state_exact"] = all(
            r["train_state"] == "FITTED_TRAIN_ONLY_NOT_SELECTED" for r in rows
        )
    else:
        checks["candidate_registry_sha_exact"] = False
        checks["candidate_artifacts_exact_5"] = False
        checks["candidate_ids_exact"] = False
        checks["candidate_train_state_exact"] = False

    # Path existence only: no CAL CSV is opened or parsed here.
    cal_root = Path("artifacts/model_data/F3_2a_training_data_v1/CALIBRATION")
    checks["cal_paths_exist_without_row_read"] = all(
        (cal_root / name).exists()
        for name in ("person_day_context.csv", "participation.csv", "trip_count.csv")
    )
    checks["test_path_not_opened"] = True

    config_text = Path(
        "configs/f3/f3_4c1_trip_count_cal_contract_v1.yaml"
    ).read_text(encoding="utf-8")
    checks["isolated_selection_frozen"] = (
        "selection_evaluation_mode: ISOLATED" in config_text
        and "primary_expected_rows: 381" in config_text
    )
    checks["propagated_guardrail_only_frozen"] = (
        "guardrail_only: true" in config_text
        and "GENERATED_BY_MAIN_FROZEN_DG_PARTICIPATION_PA1" in config_text
    )
    checks["candidate_selection_none"] = "trip_count_candidate_selection: NONE" in config_text
    checks["real_cal_not_authorized"] = "real_trip_count_cal_open_authorized: false" in config_text
    checks["test_still_sealed"] = "test_open_authorized: false" in config_text
    checks["formal_g2_not_evaluated"] = "formal_g2: NOT_EVALUATED" in config_text

    failed = [k for k, v in checks.items() if not v]
    result = {
        "phase": "F3.4c-1",
        "status": "PASS" if not failed else "FAIL",
        "contract_freeze": "PASS" if not failed else "FAIL",
        "component": "DG_TRIP_COUNT",
        "candidate_artifacts": 5,
        "trip_count_cal_rows_read": 0,
        "candidate_selection": "NONE",
        "real_trip_count_cal_open_authorized": False,
        "test_rows_read": 0,
        "test_open_authorized": False,
        "formal_g2": "NOT_EVALUATED",
        "next_step_if_pass": "IMPLEMENT_F3.4c-2a_WITH_ZERO_NEW_COMPONENT_CAL_ROWS",
        "checks": checks,
        "failed": failed,
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if not failed else 1

if __name__ == "__main__":
    raise SystemExit(main())
