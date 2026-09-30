from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

import yaml

ROOT = Path.cwd()
PARENT = "1c5ec66e4b15553996e473f46c921339f55b30d2"
CFG = ROOT / "configs/f3/f3_4f1_distance_prior_cal_contract_freeze_v1.yaml"
REG = ROOT / "configs/f3/f3_4f1_distance_prior_candidate_registry_v1.json"
FILELIST = ROOT / "docs/F3_4F1_OVERLAY_FILELIST_v1.txt"
CHECKSUMS = ROOT / "docs/F3_4F1_OVERLAY_CHECKSUMS_v1.sha256"


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], text=True).rstrip("\n")


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> None:
    cfg = yaml.safe_load(CFG.read_text())
    reg = json.loads(REG.read_text())
    expected = {x for x in FILELIST.read_text().splitlines() if x}
    actual = {x[3:] for x in git("status", "--porcelain").splitlines() if x}
    static_ok = True
    for line in CHECKSUMS.read_text().splitlines():
        if line:
            digest, rel = line.split(maxsplit=1)
            static_ok &= sha(ROOT / rel) == digest
    ids = {x["artifact_id"] for x in reg["candidates"]}
    checks = {
        "head_exact_parent": git("rev-parse", "HEAD") == PARENT,
        "branch_main": git("branch", "--show-current") == "main",
        "ahead_zero": git("rev-list", "--count", "origin/main..HEAD") == "0",
        "behind_zero": git("rev-list", "--count", "HEAD..origin/main") == "0",
        "no_staged_changes": git("diff", "--cached", "--name-only") == "",
        "scope_exact": actual == expected,
        "static_checksums": bool(static_ok),
        "candidate_count_5": reg["candidate_count"] == 5 and len(ids) == 5,
        "cal_total_2873": cfg["cal_physical_inputs"]["total_physical_rows"] == 2873,
        "cal_rows_zero": cfg["boundaries"]["cal_rows_read"] == 0,
        "primary_exact": cfg["primary"]["id"] == "M2-DIST-01"
            and cfg["primary"]["metric"] == "WEIGHTED_1D_WASSERSTEIN_DISTANCE_KM",
        "margin_025": cfg["primary"]["practical_margin_km"] == 0.25,
        "quantile_guardrails_050": all(
            cfg["summary_guardrails"][key]["tolerance"] == 0.50
            for key in (
                "p50_abs_error_worsening_km",
                "p90_abs_error_worsening_km",
                "p95_abs_error_worsening_km",
            )
        ),
        "mean_unthresholded_report_only": cfg["summary_guardrails"]["mean_abs_error"]["role"]
            == "MANDATORY_REPORT_ONLY_UNTHRESHOLDED"
            and cfg["summary_guardrails"]["mean_abs_error"]["decision_driving"] is False,
        "isolated_1147": cfg["isolated"]["target_rows"] == 1147,
        "propagated_hard_only": cfg["propagated"]["role"]
            == "HARD_RUNTIME_ADMISSIBILITY_ONLY_AFTER_PROVISIONAL_SELECTION"
            and cfg["propagated"]["propagated_distribution_selection_metric"] == "NONE",
        "upstream_time_tb2": cfg["propagated"]["upstream"]["time_schedule"] == "TIME_B_TB2",
        "replicates_32": cfg["stochastic"]["replicates"] == 32,
        "crn": cfg["stochastic"]["crn"] is True,
        "bootstrap_1000": cfg["bootstrap"]["replicates"] == 1000,
        "dedicated_runner": cfg["implementation"]["dedicated_runner_required"] is True,
        "selection_none": cfg["candidate_selection"] == "NONE",
        "distance_cal_closed": cfg["boundaries"]["real_distance_prior_cal_open_authorized"] is False,
        "test_sealed": cfg["boundaries"]["test_open_authorized"] is False,
        "g2_not_evaluated": cfg["boundaries"]["formal_g2"] == "NOT_EVALUATED",
    }
    failed = [k for k, value in checks.items() if not value]
    print(json.dumps({
        "phase": "F3.4f-1",
        "component": "DG_DISTANCE_PRIOR",
        "status": "PASS" if not failed else "FAIL",
        "contract_gate": "PASS" if not failed else "FAIL",
        "candidate_artifacts": 5,
        "candidate_selection": "NONE",
        "future_cal_physical_rows": 2873,
        "cal_rows_read": 0,
        "real_distance_prior_cal_open_authorized": False,
        "mean_guardrail_role": "REPORT_ONLY_UNTHRESHOLDED",
        "propagated_role": "HARD_RUNTIME_ADMISSIBILITY_ONLY",
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
        "next_step_if_pass": "COMMIT_CONTRACT_THEN_BUILD_SYNTHETIC_PREOPEN",
    }, indent=2, sort_keys=True))
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
