from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[1]
PARENT = "47a95201cea51d4e856acbb90a3a3e49e1cb9a5a"
CONFIG = ROOT / "configs/f3/f3_4f2b_distance_prior_real_cal_preopen_v1.yaml"
CHECKSUMS = ROOT / "docs/F3_4F2B_OVERLAY_CHECKSUMS_v1.sha256"
FILELIST = ROOT / "docs/F3_4F2B_OVERLAY_FILELIST_v1.txt"


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
    out = set()
    for line in git("status", "--porcelain", "--untracked-files=all").splitlines():
        if line:
            path = line[3:]
            if " -> " in path:
                path = path.split(" -> ", 1)[1]
            out.add(path)
    return out


def main() -> None:
    cfg = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    expected = {x.strip() for x in FILELIST.read_text(encoding="utf-8").splitlines() if x.strip()}
    actual = porcelain_paths()
    registry = pd.read_csv(ROOT / cfg["candidate_registry"]["path"])
    rows = registry[registry["component"].eq("DG_DISTANCE_PRIOR")]
    source = (ROOT / "src/simfleet_edg/evaluation/distance_prior_cal_real.py").read_text(encoding="utf-8")
    wrapper = source[source.index("def run_controlled_distance_prior_cal("):]
    direct = source[source.index("def _run_controlled_distance_prior_cal_direct("):source.index("def run_controlled_distance_prior_cal(")]
    checks = {
        "head_exact_parent": git("rev-parse", "HEAD") == PARENT,
        "branch_main": git("branch", "--show-current") == "main",
        "ahead_zero": git("rev-list", "--count", "origin/main..HEAD") == "0",
        "behind_zero": git("rev-list", "--count", "HEAD..origin/main") == "0",
        "no_staged_changes": git("diff", "--cached", "--name-only") == "",
        "overlay_scope_exact": actual == expected,
        "static_checksums_pass": checksum_pass(),
        "candidate_count_5": len(rows) == 5,
        "candidate_states_exact": set(rows["train_state"]) == {"FITTED_TRAIN_ONLY_NOT_SELECTED"},
        "cal_context_469": cfg["cal_input"]["person_day_context"]["expected_rows"] == 469,
        "cal_raw_1147": cfg["cal_input"]["distance_raw"]["expected_rows"] == 1147,
        "cal_sensitivity_1257": cfg["cal_input"]["distance_expanded_sensitivity"]["expected_rows"] == 1257,
        "cal_physical_2873": cfg["cal_input"]["expected_physical_rows"] == 2873,
        "primary_exact": cfg["evaluation"]["primary_metric"] == "M2-DIST-01",
        "margin_025": cfg["evaluation"]["practical_margin_km"] == 0.25,
        "replicates_32": cfg["evaluation"]["stochastic_replicates"] == 32,
        "bootstrap_1000": cfg["evaluation"]["household_bootstrap_replicates"] == 1000,
        "quantile_tolerance_050": cfg["summary_guardrails"]["max_worsening_km"] == 0.50,
        "mean_report_only": cfg["summary_guardrails"]["mean_role"] == "REPORT_ONLY_UNTHRESHOLDED",
        "propagated_hard_only": cfg["selection"]["propagated_role"] == "HARD_RUNTIME_ADMISSIBILITY_ONLY",
        "authorization_before_cal_io": direct.index("authorization = load_authorization") < direct.index("raw, sensitivity, cohort, input_rows, access = load_and_validate_distance_cal"),
        "authorization_before_staging_create": wrapper.index("load_authorization(authorization_path, repo_root)") < wrapper.index("_run_controlled_distance_prior_cal_direct"),
        "failure_partial_preserved": "failure.json" in source and ".partial" in source,
        "cal_rows_zero": cfg["preopen"]["cal_rows_read"] == 0,
        "selection_none": cfg["preopen"]["candidate_selection"] == "NONE",
        "real_cal_not_authorized": cfg["preopen"]["real_distance_prior_cal_open_authorized"] is False,
        "joint_not_authorized": cfg["preopen"]["joint_cal_gate_authorized"] is False,
        "test_rows_zero": cfg["preopen"]["test_rows_read"] == 0,
        "test_sealed": cfg["preopen"]["test_open_authorized"] is False,
        "g2_not_evaluated": cfg["preopen"]["formal_g2"] == "NOT_EVALUATED",
    }
    checks = {k: bool(v) for k, v in checks.items()}
    failed = [k for k, v in checks.items() if not v]
    payload = {"phase": "F3.4f-2b", "component": "DG_DISTANCE_PRIOR", "status": "PASS" if not failed else "FAIL", "preopen_gate": "PASS" if not failed else "FAIL", "checks": checks, "failed": failed, "overlay_scope": {"expected_count": len(expected), "actual_count": len(actual), "missing": sorted(expected-actual), "unexpected": sorted(actual-expected)}, "cal_rows_read": 0, "candidate_artifacts": 5, "candidate_selection": "NONE", "real_distance_prior_cal_open_authorized": False, "joint_cal_gate_authorized": False, "test_rows_read": 0, "test_open_authorized": False, "formal_g2": "NOT_EVALUATED", "next_step_if_pass": "COMMIT_PREOPEN_THEN_ISSUE_COMMIT_BOUND_A1_AUTHORIZATION"}
    print(json.dumps(payload, indent=2, sort_keys=True))
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
