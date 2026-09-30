from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

import yaml

ROOT = Path.cwd()
PARENT = "6ef56286460939e57b4a01703f56b47967615bea"
CFG = ROOT / "configs/f3/f3_4f2a_distance_prior_synthetic_preopen_v1.yaml"
FILELIST = ROOT / "docs/F3_4F2A_OVERLAY_FILELIST_v1.txt"
CHECKSUMS = ROOT / "docs/F3_4F2A_OVERLAY_CHECKSUMS_v1.sha256"


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], text=True).rstrip("\n")


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> None:
    cfg = yaml.safe_load(CFG.read_text(encoding="utf-8"))
    expected = {x for x in FILELIST.read_text(encoding="utf-8").splitlines() if x}
    actual = {x[3:] for x in git("status", "--porcelain").splitlines() if x}

    static_ok = True
    for line in CHECKSUMS.read_text(encoding="utf-8").splitlines():
        if line:
            digest, rel = line.split(maxsplit=1)
            static_ok &= sha(ROOT / rel) == digest

    checks = {
        "head_exact_parent": git("rev-parse", "HEAD") == PARENT,
        "branch_main": git("branch", "--show-current") == "main",
        "ahead_zero": git("rev-list", "--count", "origin/main..HEAD") == "0",
        "behind_zero": git("rev-list", "--count", "HEAD..origin/main") == "0",
        "no_staged_changes": git("diff", "--cached", "--name-only") == "",
        "overlay_scope_exact": actual == expected,
        "static_checksums_pass": bool(static_ok),
        "candidate_count_5": cfg["candidate_registry"]["expected_candidates"] == 5,
        "replicates_32": cfg["synthetic_protocol"]["stochastic_replicates"] == 32,
        "cal_rows_zero": cfg["boundaries"]["cal_rows_read"] == 0,
        "cal_files_empty": cfg["boundaries"]["cal_files_read"] == [],
        "selection_none": cfg["boundaries"]["candidate_selection"] == "NONE",
        "real_cal_not_authorized": cfg["boundaries"]["real_distance_prior_cal_open_authorized"] is False,
        "joint_gate_not_authorized": cfg["boundaries"]["joint_cal_gate_authorized"] is False,
        "test_rows_zero": cfg["boundaries"]["test_rows_read"] == 0,
        "test_sealed": cfg["boundaries"]["test_open_authorized"] is False,
        "g2_not_evaluated": cfg["boundaries"]["formal_g2"] == "NOT_EVALUATED",
        "candidate_rng_forbidden": cfg["synthetic_protocol"]["candidate_identity_in_rng_key"] is False,
        "selection_authorized_false": cfg["synthetic_metric_smoke"]["selection_authorized"] is False,
        "synthetic_guardrail_decision_false": cfg["summary_smoke"]["synthetic_guardrail_decision_authorized"] is False,
        "mean_report_only": cfg["summary_smoke"]["mean_role"] == "REPORT_ONLY_UNTHRESHOLDED",
    }
    failed = [k for k, v in checks.items() if not v]
    payload = {
        "phase": "F3.4f-2a",
        "component": "DG_DISTANCE_PRIOR",
        "status": "PASS" if not failed else "FAIL",
        "preopen_gate": "PASS" if not failed else "FAIL",
        "mode": "SYNTHETIC_PREOPEN",
        "candidate_artifacts": 5,
        "candidate_selection": "NONE",
        "cal_rows_read": 0,
        "real_distance_prior_cal_open_authorized": False,
        "joint_cal_gate_authorized": False,
        "test_open_authorized": False,
        "formal_g2": "NOT_EVALUATED",
        "checks": checks,
        "failed": failed,
        "overlay_scope": {
            "expected_count": len(expected),
            "actual_count": len(actual),
            "missing": sorted(expected - actual),
            "unexpected": sorted(actual - expected),
        },
        "next_step_if_pass": "RUN_SYNTHETIC_BUNDLE_THEN_PRECOMMIT_REVIEW",
    }
    print(json.dumps(payload, indent=2, sort_keys=True))
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
