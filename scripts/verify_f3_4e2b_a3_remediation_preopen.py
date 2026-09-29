from __future__ import annotations

import csv
import hashlib
import json
import subprocess
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
PARENT = "ab6c170808f77363f9812a80351d38366322b490"
FILELIST = ROOT / "docs/F3_4E2B_A3_REMEDIATION_FILELIST_v1.txt"
CHECKSUMS = ROOT / "docs/F3_4E2B_A3_REMEDIATION_CHECKSUMS_v1.sha256"
OVERLAY_CHECKSUMS = ROOT / "docs/F3_4E2B_OVERLAY_CHECKSUMS_v1.sha256"
SOURCE = ROOT / "src/simfleet_edg/evaluation/time_schedule_cal_real.py"
CONFIG = ROOT / "configs/f3/f3_4e2b_time_schedule_real_cal_preopen_v1.yaml"
REGISTRY = ROOT / "docs/F3_3_CANDIDATE_ARTIFACT_REGISTRY_v1.csv"


def git(*args: str) -> str:
    return subprocess.check_output(["git", "-C", str(ROOT), *args], text=True).rstrip("\n")


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def manifest_pass(path: Path) -> bool:
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        expected, rel = line.split(maxsplit=1)
        if sha(ROOT / rel.strip()) != expected:
            return False
    return True


def main() -> None:
    expected = sorted(x for x in FILELIST.read_text(encoding="utf-8").splitlines() if x)
    status = git("status", "--porcelain").splitlines()
    actual = sorted(line[3:] for line in status if line and not line.startswith("!!"))
    cfg = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    source = SOURCE.read_text(encoding="utf-8")
    with REGISTRY.open(encoding="utf-8", newline="") as fh:
        rows = [r for r in csv.DictReader(fh) if r["component"] == "DG_TIME_SCHEDULE"]

    time_seed_slice = source[source.index("def _time_seed"):source.index("def _candidate_feature_columns")]
    checks = {
        "head_exact_parent": git("rev-parse", "HEAD") == PARENT,
        "branch_main": git("branch", "--show-current") == "main",
        "ahead_zero": git("rev-list", "--count", "origin/main..HEAD") == "0",
        "behind_zero": git("rev-list", "--count", "HEAD..origin/main") == "0",
        "no_staged_changes": git("diff", "--cached", "--name-only") == "",
        "remediation_scope_exact": actual == expected,
        "remediation_checksums_pass": manifest_pass(CHECKSUMS),
        "updated_overlay_checksums_pass": manifest_pass(OVERLAY_CHECKSUMS),
        "candidate_count_7": len(rows) == 7,
        "candidate_selection_none": cfg["preopen"]["candidate_selection"] == "NONE",
        "time_b_exact_conditional_present": "EXACT_TIME_B_FEASIBLE_CONDITIONAL_V1" in source,
        "time_b_finite_exhaustion_removed_from_runner": "TIME_B exhausted 100 rejection attempts" not in source,
        "time_b_empty_support_fails_hard": "TIME_B has no feasible support under frozen temporal state" in source,
        "time_b_isolated_and_propagated_dispatch": source.count("_sample_time_b_precomputed(") >= 3,
        "candidate_rng_forbidden": "candidate_id" not in time_seed_slice,
        "cal_contract_still_1712": cfg["cal_input"]["expected_physical_rows"] == 1712,
        "isolated_rows_still_1243": cfg["cal_input"]["expected_isolated_time_rows"] == 1243,
        "distance_not_authorized": cfg["preopen"]["distance_prior_real_cal_authorized"] is False,
        "test_sealed": cfg["preopen"]["test_open_authorized"] is False,
        "g2_not_evaluated": cfg["preopen"]["formal_g2"] == "NOT_EVALUATED",
    }
    checks = {key: bool(value) for key, value in checks.items()}
    failed = [key for key, value in checks.items() if not value]
    payload = {
        "phase": "F3.4e-2b",
        "remediation": "A3_TIME_B_FINITE_REJECTION_REMEDIATION_V1",
        "status": "PASS" if not failed else "FAIL",
        "remediation_precommit_gate": "PASS" if not failed else "FAIL",
        "candidate_selection": "NONE",
        "formal_g2": "NOT_EVALUATED",
        "test_open_authorized": False,
        "distance_prior_real_cal_authorized": False,
        "scope": {
            "expected_count": len(expected),
            "actual_count": len(actual),
            "missing": sorted(set(expected) - set(actual)),
            "unexpected": sorted(set(actual) - set(expected)),
        },
        "checks": checks,
        "failed": failed,
        "next_step_if_pass": "COMMIT_REMEDIATION_THEN_ISSUE_NEW_COMMIT_BOUND_A4_AUTHORIZATION",
    }
    print(json.dumps(payload, indent=2, sort_keys=True))
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
