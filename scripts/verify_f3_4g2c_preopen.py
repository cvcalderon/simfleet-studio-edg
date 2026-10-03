from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
PARENT = "b0ee17a17eb6c58d655b770780cbb40e07b9b33b"
CFG = ROOT / "configs/f3/f3_4g2c_joint_real_cal_runner_preopen_v1.yaml"
FILELIST = ROOT / "docs/F3_4G2C_OVERLAY_FILELIST_v1.txt"
CHECKSUMS = ROOT / "docs/F3_4G2C_OVERLAY_CHECKSUMS_v1.sha256"


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).rstrip("\n")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def verify_overlay_checksums() -> bool:
    for line in CHECKSUMS.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        expected, rel = line.split(maxsplit=1)
        path = ROOT / rel.strip()
        if not path.is_file() or sha256_file(path) != expected:
            return False
    return True


def main() -> None:
    cfg = yaml.safe_load(CFG.read_text(encoding="utf-8"))
    expected_scope = set(FILELIST.read_text(encoding="utf-8").splitlines())
    actual_scope = {
        line[3:]
        for line in git("status", "--short").splitlines()
        if line
    }

    frozen = cfg["frozen_sources"]
    frozen_hashes = all(
        sha256_file(ROOT / spec["path"]) == spec["sha256"]
        for key, spec in frozen.items()
        if key != "authorization_boundary"
    )

    cal_root = ROOT / cfg["cal_input"]["root"]
    cal_exist = all(
        (cal_root / cfg["cal_input"][key]["filename"]).is_file()
        for key in (
            "person_day_context",
            "participation",
            "trip_count",
            "chain_days",
            "chain_transitions",
            "time_trips",
            "distance_raw",
            "distance_expanded_sensitivity",
        )
    )

    checks = {
        "head_exact_parent": git("rev-parse", "HEAD") == PARENT,
        "branch_main": git("branch", "--show-current") == "main",
        "ahead_zero": git("rev-list", "--count", "origin/main..HEAD") == "0",
        "behind_zero": git("rev-list", "--count", "HEAD..origin/main") == "0",
        "no_staged_changes": git("diff", "--cached", "--name-only") == "",
        "overlay_scope_exact": actual_scope == expected_scope,
        "overlay_checksums_pass": verify_overlay_checksums(),
        "frozen_source_hashes_exact": frozen_hashes,
        "cal_files_exist_without_content_read": cal_exist,
        "cal_rows_zero": cfg["preopen"]["cal_rows_read"] == 0,
        "future_cal_rows_6341": (
            cfg["cal_input"]["expected_total_physical_rows"] == 6341
        ),
        "authorization_before_cal_io": (
            cfg["authorization"]["authorization_before_cal_io"] is True
        ),
        "authorization_before_staging": (
            cfg["authorization"]["authorization_before_staging"] is True
        ),
        "positive_auth_not_issued": (
            cfg["preopen"]["positive_authorization_issued"] is False
        ),
        "real_cal_not_authorized": (
            cfg["preopen"]["real_cal_execution_authorized"] is False
        ),
        "joint_not_evaluated": cfg["preopen"]["joint_gate_evaluated"] is False,
        "test_rows_zero": cfg["preopen"]["test_rows_read"] == 0,
        "test_sealed": cfg["preopen"]["test_open_authorized"] is False,
        "g2_not_evaluated": cfg["preopen"]["formal_g2"] == "NOT_EVALUATED",
    }

    failed = [name for name, passed in checks.items() if not bool(passed)]
    payload = {
        "phase": "F3.4g-2c",
        "component": "DGEN_JOINT_PIPELINE",
        "status": "PASS" if not failed else "FAIL",
        "preopen_gate": "PASS" if not failed else "FAIL",
        "real_cal_runner_implemented": True,
        "cal_rows_read": 0,
        "future_cal_physical_rows": 6341,
        "positive_authorization_issued": False,
        "joint_real_cal_open_authorized": False,
        "joint_gate_evaluated": False,
        "test_rows_read": 0,
        "test_open_authorized": False,
        "formal_g2": "NOT_EVALUATED",
        "checks": {name: bool(value) for name, value in checks.items()},
        "failed": failed,
        "overlay_scope": {
            "expected_count": len(expected_scope),
            "actual_count": len(actual_scope),
            "missing": sorted(expected_scope - actual_scope),
            "unexpected": sorted(actual_scope - expected_scope),
        },
        "next_step_if_pass": "COMMIT_THEN_ISSUE_A1_COMMIT_BOUND_JOINT_REAL_CAL_AUTH",
    }
    print(json.dumps(payload, indent=2, sort_keys=True))
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
