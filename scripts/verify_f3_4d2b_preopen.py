from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[1]
PARENT = "6ea9abcd7e720d62940933aee12534797440c996"
CONFIG = ROOT / "configs/f3/f3_4d2b_activity_chain_real_cal_preopen_v1.yaml"
CHECKSUMS = ROOT / "docs/F3_4D2B_OVERLAY_CHECKSUMS_v1.sha256"
FILELIST = ROOT / "docs/F3_4D2B_OVERLAY_FILELIST_v1.txt"


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
    expected_scope = {
        line.strip()
        for line in FILELIST.read_text(encoding="utf-8").splitlines()
        if line.strip()
    }
    actual_scope = porcelain_paths()
    registry = pd.read_csv(ROOT / cfg["candidate_registry"]["path"])
    chain = registry[registry["component"].eq("DG_ACTIVITY_CHAIN")]
    source = (ROOT / "src/simfleet_edg/evaluation/activity_chain_cal_real.py").read_text(
        encoding="utf-8"
    )
    checks = {
        "head_exact_parent": git("rev-parse", "HEAD") == PARENT,
        "branch_main": git("branch", "--show-current") == "main",
        "ahead_zero": git("rev-list", "--count", "origin/main..HEAD") == "0",
        "behind_zero": git("rev-list", "--count", "HEAD..origin/main") == "0",
        "no_staged_changes": git("diff", "--cached", "--name-only") == "",
        "overlay_scope_exact": actual_scope == expected_scope,
        "static_checksums_pass": checksum_pass(),
        "candidate_count_6": len(chain) == 6,
        "candidate_states_exact": set(chain["train_state"]) == {"FITTED_TRAIN_ONLY_NOT_SELECTED"},
        "cal_context_469": cfg["cal_input"]["person_day_context"]["expected_rows"] == 469,
        "cal_chain_days_319": cfg["cal_input"]["chain_days"]["expected_rows"] == 319,
        "cal_transitions_1065": cfg["cal_input"]["chain_transitions"]["expected_rows"] == 1065,
        "cal_physical_1853": cfg["cal_input"]["expected_physical_rows"] == 1853,
        "primary_exact": cfg["evaluation"]["primary_metric"] == "WEIGHTED_NEXT_ACTIVITY_LOG_LOSS",
        "primary_margin_001": cfg["evaluation"]["practical_margin"] == 0.01,
        "replicates_32": cfg["evaluation"]["stochastic_replicates"] == 32,
        "bootstrap_1000": cfg["evaluation"]["household_bootstrap_replicates"] == 1000,
        "ci_95": cfg["evaluation"]["confidence_level"] == 0.95,
        "crn_true": cfg["evaluation"]["common_random_numbers"] is True,
        "purpose_sha_exact": cfg["precal_remediation"]["purpose_artifact_sha256"] == "ab42cf42c9568ef4f085f071299fc941d421c42337f353e00870cd05c94f94fb",
        "purpose_file_hash_exact": sha256(ROOT / cfg["precal_remediation"]["purpose_artifact"]) == cfg["precal_remediation"]["purpose_artifact_sha256"],
        "upstream_pa1": cfg["upstream"]["participation"]["artifact_id"] == "DG_PARTICIPATION::PART_A::PA1",
        "upstream_count_ref": cfg["upstream"]["trip_count"]["artifact_id"] == "DG_TRIP_COUNT::COUNT_REF::REFERENCE",
        "fixed_cohort_319": cfg["cal_input"]["expected_fixed_cohort_days"] == 319,
        "prop_primary_not_redefined": cfg["evaluation"]["propagated_primary_redefined"] is False,
        "authorization_before_cal_io": source.index("authorization = load_authorization") < source.index("days, transitions, _, input_rows, access = load_and_validate_activity_chain_cal"),
        "authorization_before_staging_create": source.index("authorization = load_authorization") < source.index("output_dir.mkdir"),
        "failure_partial_preserved": "failure.json" in source and ".partial" in source,
        "test_sealed": cfg["preopen"]["test_open_authorized"] is False,
        "test_rows_zero": cfg["preopen"]["test_rows_read"] == 0,
        "cal_rows_zero": cfg["preopen"]["cal_rows_read"] == 0,
        "selection_none": cfg["preopen"]["candidate_selection"] == "NONE",
        "real_cal_not_authorized": cfg["preopen"]["real_activity_chain_cal_open_authorized"] is False,
        "next_component_not_authorized": cfg["preopen"]["next_component_authorized"] is False,
        "g2_not_evaluated": cfg["preopen"]["formal_g2"] == "NOT_EVALUATED",
    }
    failed = [key for key, value in checks.items() if not value]
    payload = {
        "phase": "F3.4d-2b",
        "component": "DG_ACTIVITY_CHAIN",
        "status": "PASS" if not failed else "FAIL",
        "preopen_gate": "PASS" if not failed else "FAIL",
        "checks": checks,
        "failed": failed,
        "overlay_scope": {
            "expected_count": len(expected_scope),
            "actual_count": len(actual_scope),
            "missing": sorted(expected_scope - actual_scope),
            "unexpected": sorted(actual_scope - expected_scope),
        },
        "cal_rows_read": 0,
        "candidate_artifacts": 6,
        "candidate_selection": "NONE",
        "real_activity_chain_cal_open_authorized": False,
        "test_rows_read": 0,
        "test_open_authorized": False,
        "next_component_authorized": False,
        "formal_g2": "NOT_EVALUATED",
        "next_step_if_pass": "COMMIT_PREOPEN_THEN_ISSUE_COMMIT_BOUND_A1_AUTHORIZATION",
    }
    print(json.dumps(payload, indent=2, sort_keys=True))
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
