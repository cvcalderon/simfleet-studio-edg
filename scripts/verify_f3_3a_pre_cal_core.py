from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

import pandas as pd
import yaml

ROOT = Path.cwd()
CONFIG = ROOT / "configs/f3/f3_3_pre_cal_core_v1.yaml"
EXPECTED_PARENT = "a128dd29ca4d3d99545039c458ddac68159b592f"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], text=True).strip()


def main() -> None:
    cfg = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    checks: dict[str, bool] = {}
    checks["head_exact_parent"] = git("rev-parse", "HEAD") == EXPECTED_PARENT
    checks["branch_main"] = git("branch", "--show-current") == "main"
    ahead, behind = git("rev-list", "--left-right", "--count", "HEAD...origin/main").split()
    checks["ahead_zero"] = int(ahead) == 0
    checks["behind_zero"] = int(behind) == 0
    checks["no_staged_changes"] = git("diff", "--cached", "--name-only") == ""

    filelist_path = ROOT / "docs/F3_3A_PRE_CAL_CORE_OVERLAY_FILELIST_v1.txt"
    expected_overlay = {
        line.strip()
        for line in filelist_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    }
    actual_untracked = {
        line.strip()
        for line in git("ls-files", "--others", "--exclude-standard").splitlines()
        if line.strip()
    }
    actual_tracked_changes = {
        line.strip()
        for line in git("diff", "--name-only").splitlines()
        if line.strip()
    }
    tracked_overlay_paths = {
        line.strip()
        for line in git("ls-files", "--", *sorted(expected_overlay)).splitlines()
        if line.strip()
    }
    checks["tracked_overlay_changes_exact"] = (
        actual_tracked_changes == tracked_overlay_paths
    )
    checks["no_out_of_scope_tracked_changes"] = (
        actual_tracked_changes <= expected_overlay
    )
    checks["overlay_scope_exact"] = (
        actual_untracked | actual_tracked_changes
    ) == expected_overlay

    checksum_file = ROOT / "docs/F3_3A_PRE_CAL_CORE_OVERLAY_CHECKSUMS_v1.sha256"
    checksum_ok = True
    for line in checksum_file.read_text(encoding="utf-8").splitlines():
        expected, rel = line.split("  ", 1)
        path = ROOT / rel
        checksum_ok = checksum_ok and path.is_file() and sha(path) == expected
    checks["overlay_checksums_exact"] = checksum_ok

    checks["cal_unopened"] = cfg["cal_partition"] == "UNOPENED"
    checks["test_sealed"] = cfg["test_partition"] == "SEALED"
    checks["selection_none"] = cfg["candidate_selection"] == "NONE"
    checks["formal_g1_open"] = cfg["formal_g1"] == "OPEN"
    checks["formal_g2_not_evaluated"] = cfg["formal_g2"] == "NOT_EVALUATED"
    checks["32_replicates"] = cfg["stochastic_protocol"]["replicates_per_cal_person"] == 32
    checks["1000_bootstraps"] = cfg["bootstrap"]["replicates"] == 1000
    checks["bootstrap_household"] = cfg["bootstrap"]["unit"] == "HOUSEHOLD"
    checks["bootstrap_paired"] = cfg["bootstrap"]["paired"] is True
    checks["confidence_95"] = cfg["bootstrap"]["confidence_level"] == 0.95
    checks["part_b_5fold"] = cfg["part_b_calibration"]["folds"] == 5

    for witness, spec in cfg["source_witnesses"].items():
        p = ROOT / spec["path"]
        checks[f"witness:{witness}"] = p.is_file() and sha(p) == spec["sha256"]

    registry_path = ROOT / cfg["candidate_registry"]["path"]
    registry = pd.read_csv(registry_path, dtype={"grid_id": str})
    checks["registry_sha"] = sha(registry_path) == cfg["candidate_registry"]["sha256"]
    checks["registry_rows_31"] = len(registry) == 31
    counts = registry.groupby("component").size().to_dict()
    checks["registry_component_counts"] = counts == cfg["candidate_registry"]["expected_rows_by_component"]
    checks["registry_all_unselected"] = registry["train_state"].eq("FITTED_TRAIN_ONLY_NOT_SELECTED").all()
    checks["registry_roles_exact"] = set(registry["role"]) == {
        "REFERENCE_BASELINE", "CORE_CANDIDATE_A", "CORE_CHALLENGER_B"
    }

    run_checks = 0
    for row in registry.itertuples(index=False):
        run_root = ROOT / "artifacts/runs" / row.official_run_dir
        model = run_root / row.model_relpath
        manifest = run_root / row.artifact_manifest_relpath
        ok = model.is_file() and manifest.is_file()
        ok = ok and sha(model) == row.model_sha256 and sha(manifest) == row.manifest_sha256
        if ok:
            art = json.loads(manifest.read_text(encoding="utf-8"))
            ok = art.get("status") == "FITTED_TRAIN_ONLY_NOT_SELECTED"
            ok = ok and art.get("cal_metrics") is None
            ok = ok and art.get("selection_decision") == "NOT_EVALUATED"
            ok = ok and art.get("test_partition_consumed") is False
            if "calibration_partition_consumed" in art:
                ok = ok and art["calibration_partition_consumed"] is False
            if "candidate_selection_performed" in art:
                ok = ok and art["candidate_selection_performed"] is False
        checks[f"artifact:{row.artifact_id}"] = ok
        run_checks += 1

    expected_margins = {
        "DG_PARTICIPATION": 0.005,
        "DG_TRIP_COUNT": 0.05,
        "DG_ACTIVITY_CHAIN": 0.01,
        "DG_TIME_SCHEDULE": 0.005,
        "DG_DISTANCE_PRIOR": 0.25,
    }
    checks["promotion_margins_exact"] = cfg["promotion_margins"] == expected_margins
    checks["cal_open_blocked"] = cfg["cal_opening_blocker"]["state"] == "BLOCKED"
    checks["core_must_not_read_cal"] = cfg["cal_opening_blocker"]["core_overlay_must_not_read_cal"] is True

    checks = {key: bool(value) for key, value in checks.items()}
    failed = [k for k, v in checks.items() if not v]
    print(json.dumps({
        "status": "PASS" if not failed else "FAIL",
        "checks": checks,
        "artifact_checks": run_checks,
        "failed": failed,
        "candidate_rows": len(registry),
        "cal_rows_read": 0,
    }, indent=2, sort_keys=True))
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
