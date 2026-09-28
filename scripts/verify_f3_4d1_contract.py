from __future__ import annotations

import json
import subprocess
from pathlib import Path

import yaml

ROOT = Path.cwd()
PARENT = "57b54fbbab84ef578154ff55e29656121369c286"
FILELIST = ROOT / "docs/F3_4D1_OVERLAY_FILELIST_v1.txt"
CFG = ROOT / "configs/f3/f3_4d1_activity_chain_cal_contract_v1.yaml"


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], text=True).rstrip("\n")


def main() -> None:
    cfg = yaml.safe_load(CFG.read_text(encoding="utf-8"))
    status_lines = [x for x in git("status", "--porcelain").splitlines() if x]
    scope = {x[3:] for x in status_lines}
    expected_scope = {
        x.strip()
        for x in FILELIST.read_text(encoding="utf-8").splitlines()
        if x.strip()
    }
    candidates = cfg["candidate_universe"]
    ids = [x["artifact_id"] for x in candidates]

    checks = {
        "head_exact_parent": git("rev-parse", "HEAD") == PARENT,
        "branch_main": git("branch", "--show-current") == "main",
        "ahead_zero": git("rev-list", "--count", "origin/main..HEAD") == "0",
        "behind_zero": git("rev-list", "--count", "HEAD..origin/main") == "0",
        "no_staged_changes": git("diff", "--cached", "--name-only") == "",
        "overlay_scope_exact": scope == expected_scope,
        "candidate_count_6": len(candidates) == 6,
        "candidate_ids_unique": len(ids) == len(set(ids)),
        "candidate_states_exact": all(
            x["state"] == "FITTED_TRAIN_ONLY_NOT_SELECTED" for x in candidates
        ),
        "reference_exact": ids[0]
        == "DG_ACTIVITY_CHAIN::CHAIN_REF::REFERENCE",
        "chain_a_exact": ids[1:3] == [
            "DG_ACTIVITY_CHAIN::CHAIN_A::CHA1",
            "DG_ACTIVITY_CHAIN::CHAIN_A::CHA2",
        ],
        "chain_b_exact": ids[3:] == [
            "DG_ACTIVITY_CHAIN::CHAIN_B::CHB1",
            "DG_ACTIVITY_CHAIN::CHAIN_B::CHB2",
            "DG_ACTIVITY_CHAIN::CHAIN_B::CHB3",
        ],
        "upstream_participation_pa1_main_frozen": cfg["upstream"]["participation"][
            "artifact_id"
        ]
        == "DG_PARTICIPATION::PART_A::PA1"
        and cfg["upstream"]["participation"]["state"] == "MAIN_FROZEN",
        "upstream_trip_count_ref_main_frozen": cfg["upstream"]["trip_count"][
            "artifact_id"
        ]
        == "DG_TRIP_COUNT::COUNT_REF::REFERENCE"
        and cfg["upstream"]["trip_count"]["state"] == "MAIN_FROZEN",
        "cal_chain_days_319": cfg["cal_input"]["chain_days"]["expected_rows"] == 319,
        "cal_transitions_1065": cfg["cal_input"]["chain_transitions"][
            "expected_rows"
        ]
        == 1065,
        "primary_exact": cfg["evaluation"]["primary"]["metric"]
        == "WEIGHTED_NEXT_ACTIVITY_LOG_LOSS",
        "primary_margin_001": cfg["evaluation"]["primary"]["practical_margin"]
        == 0.01,
        "isolated_selection_surface": cfg["evaluation"]["isolated"]["purpose"]
        == "CANDIDATE_SELECTION_AND_PROMOTION",
        "propagated_guardrail_only": cfg["evaluation"]["propagated"]["purpose"]
        == "POST_SELECTION_GUARDRAIL_ONLY",
        "propagated_primary_not_redefined": cfg["evaluation"]["propagated"][
            "primary_metric_redefined"
        ]
        is False,
        "guardrail_ids_exact": [x["metric"] for x in cfg["guardrails"]]
        == ["M2-PURP-01", "M2-TRANS-01", "M2-RET-01"],
        "guardrail_tolerances_exact": [
            x["worsening_tolerance"] for x in cfg["guardrails"]
        ]
        == [0.005, 0.005, 0.01],
        "replicates_32": cfg["stochastic_protocol"]["replicates"] == 32,
        "crn_true": cfg["stochastic_protocol"]["common_random_numbers"] is True,
        "bootstrap_1000": cfg["stochastic_protocol"]["bootstrap"]["replicates"]
        == 1000,
        "ci_95": cfg["stochastic_protocol"]["bootstrap"]["confidence_level"]
        == 0.95,
        "real_cal_not_authorized": cfg["boundaries"]["real_cal_open_authorized"]
        is False,
        "cal_rows_zero": cfg["boundaries"]["cal_rows_read_by_this_phase"] == 0,
        "candidate_selection_none": cfg["selection"]["candidate_selection_at_entry"]
        == "NONE",
        "test_sealed": cfg["boundaries"]["test_open_authorized"] is False,
        "test_rows_zero": cfg["boundaries"]["test_rows_read"] == 0,
        "next_component_not_authorized": cfg["boundaries"][
            "next_component_authorized"
        ]
        is False,
        "g2_not_evaluated": cfg["boundaries"]["formal_g2"] == "NOT_EVALUATED",
    }
    failed = [k for k, v in checks.items() if not v]
    out = {
        "phase": "F3.4d-1",
        "component": "DG_ACTIVITY_CHAIN",
        "status": "PASS" if not failed else "FAIL",
        "contract_gate": "PASS" if not failed else "FAIL",
        "candidate_artifacts": len(candidates),
        "candidate_selection": "NONE",
        "cal_rows_read": 0,
        "real_cal_open_authorized": False,
        "test_rows_read": 0,
        "test_open_authorized": False,
        "formal_g2": "NOT_EVALUATED",
        "next_step_if_pass": "COMMIT_CONTRACT_THEN_PREPARE_F3.4d-2a_SYNTHETIC_PREOPEN",
        "checks": checks,
        "failed": failed,
        "overlay_scope": {
            "expected_count": len(expected_scope),
            "actual_count": len(scope),
            "missing": sorted(expected_scope - scope),
            "unexpected": sorted(scope - expected_scope),
        },
    }
    print(json.dumps(out, indent=2, sort_keys=True))
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
