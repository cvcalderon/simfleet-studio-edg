from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
PARENT = "30c6340baccac11555800b77d12c4f6d80a89392"
CFG = ROOT / "configs/f3/f3_4g2b_joint_real_cal_auth_preopen_v1.yaml"
TEMPLATE = ROOT / "configs/f3/f3_4g2b_joint_real_cal_authorization_TEMPLATE_v1.json"
FILELIST = ROOT / "docs/F3_4G2B_OVERLAY_FILELIST_v1.txt"
CHECKSUMS = ROOT / "docs/F3_4G2B_OVERLAY_CHECKSUMS_v1.sha256"


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).rstrip("\n")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def verify_static_checksums() -> bool:
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
    template = json.loads(TEMPLATE.read_text(encoding="utf-8"))
    expected_scope = set(FILELIST.read_text(encoding="utf-8").splitlines())
    actual_scope = {
        line[3:]
        for line in git("status", "--short").splitlines()
        if line
    }

    cal_root = ROOT / cfg["future_real_cal"]["root"]
    cal_files_exist = all(
        (cal_root / name).is_file()
        for name in cfg["future_real_cal"]["allowed_files"]
    )

    checks = {
        "head_exact_parent": git("rev-parse", "HEAD") == PARENT,
        "branch_main": git("branch", "--show-current") == "main",
        "ahead_zero": git("rev-list", "--count", "origin/main..HEAD") == "0",
        "behind_zero": git("rev-list", "--count", "HEAD..origin/main") == "0",
        "no_staged_changes": git("diff", "--cached", "--name-only") == "",
        "overlay_scope_exact": actual_scope == expected_scope,
        "static_checksums_pass": verify_static_checksums(),
        "cal_files_exist_without_content_read": cal_files_exist,
        "cal_rows_zero": cfg["future_real_cal"]["rows_read_in_f3_4g2b"] == 0,
        "future_rows_6341": (
            cfg["future_real_cal"]["expected_total_physical_rows"] == 6341
        ),
        "template_negative_real_cal": (
            template["joint_real_cal_open_authorized"] is False
        ),
        "template_negative_joint_gate": (
            template["joint_gate_evaluation_authorized"] is False
        ),
        "template_commit_placeholder": (
            template["authorized_implementation_commit"]
            == "__FILL_AFTER_F3_4G2B_PREOPEN_COMMIT__"
        ),
        "template_files_exact": set(template["allowed_cal_files"])
        == set(cfg["future_real_cal"]["allowed_files"]),
        "authorization_before_cal_io": (
            cfg["authorization_boundary"]["authorization_must_precede_cal_path_open"]
            is True
        ),
        "authorization_before_staging": (
            cfg["authorization_boundary"][
                "authorization_must_precede_output_staging_creation"
            ]
            is True
        ),
        "external_positive_auth": (
            cfg["authorization_boundary"]["positive_authorization_file_must_be_external"]
            is True
        ),
        "test_sealed": cfg["boundaries"]["test_open_authorized"] is False,
        "test_rows_zero": cfg["boundaries"]["test_rows_read"] == 0,
        "g2_not_evaluated": cfg["boundaries"]["formal_g2"] == "NOT_EVALUATED",
        "joint_real_cal_closed": (
            cfg["boundaries"]["joint_real_cal_open_authorized"] is False
        ),
        "joint_not_evaluated": cfg["boundaries"]["joint_gate_evaluated"] is False,
    }

    failed = [name for name, value in checks.items() if not bool(value)]
    payload = {
        "phase": "F3.4g-2b",
        "component": "DGEN_JOINT_PIPELINE",
        "status": "PASS" if not failed else "FAIL",
        "preopen_gate": "PASS" if not failed else "FAIL",
        "cal_rows_read": 0,
        "future_cal_physical_rows": 6341,
        "authorization_template_positive": False,
        "real_cal_runner_implemented": False,
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
        "next_step_if_pass": "COMMIT_THEN_IMPLEMENT_F3_4G2C_REAL_CAL_RUNNER_PREOPEN",
    }
    print(json.dumps(payload, indent=2, sort_keys=True))
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
