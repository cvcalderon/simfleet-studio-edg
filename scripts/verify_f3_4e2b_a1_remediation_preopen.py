from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[1]
PARENT = "13e38ac5965ac2f3b7f49a4d21fa375d0edc9092"
CONFIG = ROOT / "configs/f3/f3_4e2b_time_schedule_real_cal_preopen_v1.yaml"
REMEDIATION_CHECKSUMS = ROOT / "docs/F3_4E2B_A1_REMEDIATION_CHECKSUMS_v1.sha256"
REMEDIATION_FILELIST = ROOT / "docs/F3_4E2B_A1_REMEDIATION_FILELIST_v1.txt"
OVERLAY_CHECKSUMS = ROOT / "docs/F3_4E2B_OVERLAY_CHECKSUMS_v1.sha256"


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).rstrip("\n")


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def checksum_pass(manifest: Path) -> bool:
    for line in manifest.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        expected, rel = line.split(maxsplit=1)
        if sha256(ROOT / rel.strip()) != expected:
            return False
    return True


def porcelain_paths() -> set[str]:
    paths: set[str] = set()
    for line in git("status", "--porcelain", "--untracked-files=all").splitlines():
        if not line:
            continue
        path = line[3:]
        if " -> " in path:
            path = path.split(" -> ", 1)[1]
        paths.add(path)
    return paths


def main() -> None:
    cfg = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    expected = {line.strip() for line in REMEDIATION_FILELIST.read_text(encoding="utf-8").splitlines() if line.strip()}
    actual = porcelain_paths()
    registry = pd.read_csv(ROOT / cfg["candidate_registry"]["path"])
    time_rows = registry[registry["component"].eq("DG_TIME_SCHEDULE")]
    source = (ROOT / "src/simfleet_edg/evaluation/time_schedule_cal_real.py").read_text(encoding="utf-8")
    checks = {
        "head_exact_parent": git("rev-parse", "HEAD") == PARENT,
        "branch_main": git("branch", "--show-current") == "main",
        "ahead_zero": git("rev-list", "--count", "origin/main..HEAD") == "0",
        "behind_zero": git("rev-list", "--count", "HEAD..origin/main") == "0",
        "no_staged_changes": git("diff", "--cached", "--name-only") == "",
        "remediation_scope_exact": actual == expected,
        "remediation_checksums_pass": checksum_pass(REMEDIATION_CHECKSUMS),
        "updated_overlay_checksums_pass": checksum_pass(OVERLAY_CHECKSUMS),
        "candidate_count_7": len(time_rows) == 7,
        "candidate_states_exact": set(time_rows["train_state"]) == {"FITTED_TRAIN_ONLY_NOT_SELECTED"},
        "registry_sha_exact": sha256(ROOT / cfg["candidate_registry"]["path"]) == cfg["candidate_registry"]["sha256"],
        "missing_context_semantics_present": 'MISSING_CONTEXT = "__MISSING_CONTEXT__"' in source,
        "missing_context_no_k_invention": "return None" in source[source.index("def _trips_remaining_after_current"):source.index("def _time_seed")],
        "source_target_identity_validation_present": "arrival/departure/day-offset/duration identity mismatch" in source,
        "cal_contract_still_1712": cfg["cal_input"]["expected_physical_rows"] == 1712,
        "isolated_rows_still_1243": cfg["cal_input"]["expected_isolated_time_rows"] == 1243,
        "candidate_selection_none": cfg["preopen"]["candidate_selection"] == "NONE",
        "distance_not_authorized": cfg["preopen"]["distance_prior_real_cal_authorized"] is False,
        "test_sealed": cfg["preopen"]["test_open_authorized"] is False,
        "g2_not_evaluated": cfg["preopen"]["formal_g2"] == "NOT_EVALUATED",
    }
    checks = {k: bool(v) for k, v in checks.items()}
    failed = [k for k, v in checks.items() if not v]
    payload = {
        "phase": "F3.4e-2b",
        "remediation": "A1_RUNTIME_REMEDIATION_V1",
        "status": "PASS" if not failed else "FAIL",
        "remediation_precommit_gate": "PASS" if not failed else "FAIL",
        "checks": checks,
        "failed": failed,
        "scope": {
            "expected_count": len(expected),
            "actual_count": len(actual),
            "missing": sorted(expected - actual),
            "unexpected": sorted(actual - expected),
        },
        "candidate_selection": "NONE",
        "distance_prior_real_cal_authorized": False,
        "test_open_authorized": False,
        "formal_g2": "NOT_EVALUATED",
        "next_step_if_pass": "COMMIT_REMEDIATION_THEN_ISSUE_NEW_COMMIT_BOUND_A2_AUTHORIZATION",
    }
    print(json.dumps(payload, indent=2, sort_keys=True))
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
