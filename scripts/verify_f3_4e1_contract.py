from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

import yaml

ROOT = Path.cwd()
PARENT = "35ad02b2e024becddc2ef4164784e36a84486222"
CFG = ROOT / "configs/f3/f3_4e1_time_schedule_cal_contract_freeze_v1.yaml"
REG = ROOT / "configs/f3/f3_4e1_time_schedule_candidate_registry_v1.json"
FILELIST = ROOT / "docs/F3_4E1_OVERLAY_FILELIST_v1.txt"
CHECKSUMS = ROOT / "docs/F3_4E1_OVERLAY_CHECKSUMS_v1.sha256"


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
        "candidate_count_7": reg["candidate_count"] == 7 and len(ids) == 7,
        "cal_1712": cfg["cal_physical_inputs"]["total_rows"] == 1712,
        "cal_rows_zero": cfg["boundaries"]["cal_rows_read"] == 0,
        "primary_exact": cfg["primary"]["id"] == "M2-TIME-01"
            and cfg["primary"]["metric"] == "DEPARTURE_HOUR_DISTRIBUTION_TVD",
        "margin_0005": cfg["primary"]["practical_margin"] == 0.005,
        "mean32": cfg["primary"]["stochastic_score"] == "MEAN_OVER_32_PAIRED_REPLICATES",
        "hard_zero": cfg["hard_guardrail"]["metric"] == "TEMPORAL_INVARIANT_VIOLATIONS"
            and cfg["hard_guardrail"]["required"] == 0,
        "aux_report_only": cfg["auxiliary"]["role"] == "REPORT_ONLY"
            and cfg["auxiliary"]["drives_selection"] is False,
        "isolated_1243": cfg["isolated"]["target_rows"] == 1243,
        "prop_fixed": cfg["propagated"]["fixed_cohort"]
            == "UNIQUE_CONTEXT_ROW_ID_PRESENT_IN_CAL_TIME_TRIPS",
        "upstream_cha2": cfg["propagated"]["upstream"]["activity_chain"]
            == "DG_ACTIVITY_CHAIN::CHAIN_A::CHA2",
        "replicates_32": cfg["stochastic"]["replicates"] == 32,
        "crn": cfg["stochastic"]["crn"] is True,
        "bootstrap_1000": cfg["bootstrap"]["replicates"] == 1000,
        "selection_none": cfg["candidate_selection"] == "NONE",
        "distance_closed": cfg["boundaries"]["distance_prior_real_cal_authorized"] is False,
        "test_sealed": cfg["boundaries"]["test_open_authorized"] is False,
        "g2_not_evaluated": cfg["boundaries"]["formal_g2"] == "NOT_EVALUATED",
    }
    failed = [k for k,v in checks.items() if not v]
    print(json.dumps({
        "phase":"F3.4e-1",
        "component":"DG_TIME_SCHEDULE",
        "status":"PASS" if not failed else "FAIL",
        "contract_gate":"PASS" if not failed else "FAIL",
        "candidate_artifacts":7,
        "candidate_selection":"NONE",
        "future_cal_physical_rows":1712,
        "cal_rows_read":0,
        "real_time_schedule_cal_open_authorized":False,
        "distance_prior_real_cal_authorized":False,
        "test_open_authorized":False,
        "formal_g2":"NOT_EVALUATED",
        "checks":checks,
        "failed":failed,
        "overlay_scope":{
            "expected_count":len(expected),
            "actual_count":len(actual),
            "missing":sorted(expected-actual),
            "unexpected":sorted(actual-expected),
        },
        "next_step_if_pass":"COMMIT_CONTRACT_THEN_BUILD_SYNTHETIC_PREOPEN",
    }, indent=2, sort_keys=True))
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
