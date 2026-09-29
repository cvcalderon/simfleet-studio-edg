from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[1]
PARENT = "fc238749d5972ee189f3223affd8f4daa9f2b186"
CONFIG = ROOT / "configs/f3/f3_4e2b_time_schedule_real_cal_preopen_v1.yaml"
CHECKSUMS = ROOT / "docs/F3_4E2B_OVERLAY_CHECKSUMS_v1.sha256"
FILELIST = ROOT / "docs/F3_4E2B_OVERLAY_FILELIST_v1.txt"


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).rstrip("\n")


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def checksum_pass() -> bool:
    for line in CHECKSUMS.read_text(encoding="utf-8").splitlines():
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
    expected = {line.strip() for line in FILELIST.read_text(encoding="utf-8").splitlines() if line.strip()}
    actual = porcelain_paths()
    registry = pd.read_csv(ROOT / cfg["candidate_registry"]["path"])
    time_rows = registry[registry["component"].eq("DG_TIME_SCHEDULE")]
    source = (ROOT / "src/simfleet_edg/evaluation/time_schedule_cal_real.py").read_text(encoding="utf-8")
    wrapper = source[source.index("def run_controlled_time_schedule_cal(") :]
    checks = {
        "head_exact_parent": git("rev-parse", "HEAD") == PARENT,
        "branch_main": git("branch", "--show-current") == "main",
        "ahead_zero": git("rev-list", "--count", "origin/main..HEAD") == "0",
        "behind_zero": git("rev-list", "--count", "HEAD..origin/main") == "0",
        "no_staged_changes": git("diff", "--cached", "--name-only") == "",
        "overlay_scope_exact": actual == expected,
        "static_checksums_pass": checksum_pass(),
        "contract_sha_exact": sha256(ROOT / cfg["contract"]["path"]) == cfg["contract"]["sha256"],
        "registry_sha_exact": sha256(ROOT / cfg["candidate_registry"]["path"]) == cfg["candidate_registry"]["sha256"],
        "snapshot_sha_exact": sha256(ROOT / cfg["candidate_registry"]["frozen_snapshot"]) == cfg["candidate_registry"]["frozen_snapshot_sha256"],
        "candidate_count_7": len(time_rows) == 7,
        "candidate_states_exact": set(time_rows["train_state"]) == {"FITTED_TRAIN_ONLY_NOT_SELECTED"},
        "cal_context_469": cfg["cal_input"]["person_day_context"]["expected_rows"] == 469,
        "cal_time_rows_1243": cfg["cal_input"]["time_trips"]["expected_rows"] == 1243,
        "cal_physical_1712": cfg["cal_input"]["expected_physical_rows"] == 1712,
        "fixed_cohort_378": cfg["cal_input"]["expected_fixed_cohort_days"] == 378,
        "primary_exact": cfg["evaluation"]["primary_metric"] == "M2-TIME-01",
        "primary_tvd": cfg["evaluation"]["primary_statistic"] == "DEPARTURE_HOUR_DISTRIBUTION_TVD",
        "primary_margin_0005": cfg["evaluation"]["practical_margin"] == 0.005,
        "replicates_32": cfg["evaluation"]["stochastic_replicates"] == 32,
        "bootstrap_1000": cfg["evaluation"]["household_bootstrap_replicates"] == 1000,
        "ci_95": cfg["evaluation"]["confidence_level"] == 0.95,
        "crn_true": cfg["evaluation"]["common_random_numbers"] is True,
        "prop_primary_not_redefined": cfg["evaluation"]["propagated_primary_redefined"] is False,
        "upstream_pa1": cfg["upstream"]["participation"]["artifact_id"] == "DG_PARTICIPATION::PART_A::PA1",
        "upstream_count_ref": cfg["upstream"]["trip_count"]["artifact_id"] == "DG_TRIP_COUNT::COUNT_REF::REFERENCE",
        "upstream_cha2": cfg["upstream"]["activity_chain"]["artifact_id"] == "DG_ACTIVITY_CHAIN::CHAIN_A::CHA2",
        "candidate_rng_forbidden": cfg["rng"]["candidate_identity_in_rng_key"] is False,
        "authorization_before_cal_io": source.index("authorization = load_authorization") < source.index("merged, cohort, input_rows, access = load_and_validate_time_schedule_cal"),
        "authorization_before_staging_create": wrapper.index("load_authorization(authorization_path, repo_root)") < wrapper.index("manifest = _run_controlled_time_schedule_cal_direct("),
        "failure_partial_preserved": "failure.json" in source and ".partial" in source,
        "cal_rows_zero": cfg["preopen"]["cal_rows_read"] == 0,
        "selection_none": cfg["preopen"]["candidate_selection"] == "NONE",
        "real_cal_not_authorized": cfg["preopen"]["real_time_schedule_cal_open_authorized"] is False,
        "distance_not_authorized": cfg["preopen"]["distance_prior_real_cal_authorized"] is False,
        "test_rows_zero": cfg["preopen"]["test_rows_read"] == 0,
        "test_sealed": cfg["preopen"]["test_open_authorized"] is False,
        "g2_not_evaluated": cfg["preopen"]["formal_g2"] == "NOT_EVALUATED",
    }
    checks = {k: bool(v) for k, v in checks.items()}
    failed = [key for key, value in checks.items() if not value]
    payload = {
        "phase": "F3.4e-2b",
        "component": "DG_TIME_SCHEDULE",
        "status": "PASS" if not failed else "FAIL",
        "preopen_gate": "PASS" if not failed else "FAIL",
        "checks": checks,
        "failed": failed,
        "overlay_scope": {
            "expected_count": len(expected),
            "actual_count": len(actual),
            "missing": sorted(expected - actual),
            "unexpected": sorted(actual - expected),
        },
        "cal_rows_read": 0,
        "candidate_artifacts": 7,
        "candidate_selection": "NONE",
        "real_time_schedule_cal_open_authorized": False,
        "distance_prior_real_cal_authorized": False,
        "test_rows_read": 0,
        "test_open_authorized": False,
        "formal_g2": "NOT_EVALUATED",
        "next_step_if_pass": "COMMIT_PREOPEN_THEN_ISSUE_COMMIT_BOUND_A1_AUTHORIZATION",
    }
    print(json.dumps(payload, indent=2, sort_keys=True))
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
