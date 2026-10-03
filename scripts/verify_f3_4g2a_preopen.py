from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
PARENT = "19e903ffbc4cb914d2b70d637bae2e82d1200e30"
CFG = ROOT / "configs/f3/f3_4g2a_joint_synthetic_preopen_v1.yaml"
JOINT = ROOT / "configs/f3/f3_4g1_joint_cal_contract_freeze_v1.yaml"
REGISTRY = ROOT / "configs/f3/f3_4g1_joint_pipeline_registry_v1.json"
FILELIST = ROOT / "docs/F3_4G2A_OVERLAY_FILELIST_v1.txt"
CHECKSUMS = ROOT / "docs/F3_4G2A_OVERLAY_CHECKSUMS_v1.sha256"


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).rstrip("\n")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def status_scope() -> set[str]:
    output = git("status", "--short")
    return {line[3:] for line in output.splitlines() if line}


def verify_sha_manifest() -> bool:
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
    joint = yaml.safe_load(JOINT.read_text(encoding="utf-8"))
    registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
    expected_scope = set(FILELIST.read_text(encoding="utf-8").splitlines())
    actual_scope = status_scope()

    cal_root = ROOT / joint["cal_access"]["root"]
    cal_files_exist = all(
        (cal_root / filename).is_file()
        for filename in joint["cal_access"]["allowed_files"]
    )

    checks = {
        "head_exact_parent": git("rev-parse", "HEAD") == PARENT,
        "branch_main": git("branch", "--show-current") == "main",
        "ahead_zero": git("rev-list", "--count", "origin/main..HEAD") == "0",
        "behind_zero": git("rev-list", "--count", "HEAD..origin/main") == "0",
        "no_staged_changes": git("diff", "--cached", "--name-only") == "",
        "overlay_scope_exact": actual_scope == expected_scope,
        "static_checksums_pass": verify_sha_manifest(),
        "joint_contract_parent_exact": cfg["required_parent_commit"] == PARENT,
        "pipeline_slots_10": (
            len(registry["selected_pipeline"]) + len(registry["all_reference_pipeline"])
            == 10
        ),
        "replicates_32": cfg["synthetic_protocol"]["stochastic_replicates"] == 32,
        "master_seed_exact": cfg["synthetic_protocol"]["master_seed"] == 20260926,
        "crn": cfg["synthetic_protocol"]["common_random_numbers"] is True,
        "same_seed_schedule": (
            cfg["synthetic_protocol"]["same_seed_schedule_across_pipelines"] is True
        ),
        "cal_files_exist_without_read": cal_files_exist,
        "cal_rows_zero": cfg["access_boundaries"]["cal_rows_read"] == 0,
        "joint_real_cal_closed": (
            cfg["access_boundaries"]["joint_real_cal_open_authorized"] is False
        ),
        "joint_not_evaluated": (
            cfg["access_boundaries"]["joint_gate_evaluated"] is False
        ),
        "test_rows_zero": cfg["access_boundaries"]["test_rows_read"] == 0,
        "test_sealed": cfg["access_boundaries"]["test_open_authorized"] is False,
        "g2_not_evaluated": cfg["access_boundaries"]["formal_g2"] == "NOT_EVALUATED",
        "selection_forbidden": cfg["synthetic_smoke"]["selection_authorized"] is False,
        "synthetic_metrics_nondecision": (
            cfg["synthetic_smoke"]["metric_smoke_decision_authorized"] is False
        ),
    }

    failed = [name for name, value in checks.items() if not bool(value)]
    payload = {
        "phase": "F3.4g-2a",
        "component": "DGEN_JOINT_PIPELINE",
        "mode": "SYNTHETIC_PREOPEN",
        "status": "PASS" if not failed else "FAIL",
        "preopen_gate": "PASS" if not failed else "FAIL",
        "cal_rows_read": 0,
        "pipeline_artifact_slots": 10,
        "stochastic_replicates": 32,
        "candidate_selection": "NONE",
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
        "next_step_if_pass": "RUN_SYNTHETIC_BUNDLE_THEN_PRECOMMIT_REVIEW",
    }
    print(json.dumps(payload, indent=2, sort_keys=True))
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
