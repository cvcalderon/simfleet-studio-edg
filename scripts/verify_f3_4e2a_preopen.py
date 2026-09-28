from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

import yaml

ROOT = Path.cwd()
PARENT = "eaf54f0e8f49ee784387b5887bcbb27c282e5849"
CFG = ROOT / "configs/f3/f3_4e2a_time_schedule_synthetic_preopen_v1.yaml"
FILELIST = ROOT / "docs/F3_4E2A_OVERLAY_FILELIST_v1.txt"
CHECKSUMS = ROOT / "docs/F3_4E2A_OVERLAY_CHECKSUMS_v1.sha256"


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
        "candidate_count_7": cfg["candidate_registry"]["expected_candidates"] == 7,
        "replicates_32": cfg["synthetic_protocol"]["stochastic_replicates"] == 32,
        "cal_rows_zero": cfg["boundaries"]["cal_rows_read"] == 0,
        "cal_files_empty": cfg["boundaries"]["cal_files_read"] == [],
        "selection_none": cfg["boundaries"]["candidate_selection"] == "NONE",
        "real_cal_not_authorized": cfg["boundaries"]["real_time_schedule_cal_open_authorized"] is False,
        "distance_not_authorized": cfg["boundaries"]["distance_prior_real_cal_authorized"] is False,
        "test_rows_zero": cfg["boundaries"]["test_rows_read"] == 0,
        "test_sealed": cfg["boundaries"]["test_open_authorized"] is False,
        "g2_not_evaluated": cfg["boundaries"]["formal_g2"] == "NOT_EVALUATED",
        "candidate_rng_forbidden": cfg["synthetic_protocol"]["candidate_identity_in_rng_key"] is False,
        "selection_authorized_false": cfg["synthetic_metric_smoke"]["selection_authorized"] is False,
        "temporal_policy_exact": cfg["temporal_smoke"]["temporal_invariant_policy"]
        == "REJECT_INVALID_DRAW_NO_SILENT_REPAIR",
    }
    failed = [k for k, v in checks.items() if not v]
    payload = {
        "phase": "F3.4e-2a",
        "component": "DG_TIME_SCHEDULE",
        "status": "PASS" if not failed else "FAIL",
        "preopen_gate": "PASS" if not failed else "FAIL",
        "mode": "SYNTHETIC_PREOPEN",
        "candidate_artifacts": 7,
        "candidate_selection": "NONE",
        "cal_rows_read": 0,
        "real_time_schedule_cal_open_authorized": False,
        "distance_prior_real_cal_authorized": False,
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
        "next_step_if_pass": "RUN_SYNTHETIC_BUNDLE_THEN_COMMIT",
    }
    print(json.dumps(payload, indent=2, sort_keys=True))
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
