from __future__ import annotations

import json
import subprocess
from pathlib import Path

import yaml

ROOT = Path.cwd()
PARENT = "806c1b3e09530645163fc6983b9a76c0baf4efd1"

FILELIST = ROOT / "docs/F3_4C2BR1_OVERLAY_FILELIST_v1.txt"


def git(*args: str) -> str:
    # Preserve leading whitespace: it is semantic in `git status --porcelain`.
    return subprocess.check_output(["git", *args], text=True).rstrip("\n")


def main() -> None:
    cfg = yaml.safe_load(
        (
            ROOT / "configs/f3/f3_4c2a_trip_count_real_cal_preopen_v1.yaml"
        ).read_text(encoding="utf-8")
    )
    rem = yaml.safe_load(
        (
            ROOT
            / "configs/f3/f3_4c2br1_trip_count_observability_remediation_v1.yaml"
        ).read_text(encoding="utf-8")
    )

    status_lines = [
        line for line in git("status", "--porcelain").splitlines() if line
    ]
    scope = {line[3:] for line in status_lines}
    expected_scope = {
        line.strip()
        for line in FILELIST.read_text(encoding="utf-8").splitlines()
        if line.strip()
    }
    staged = git("diff", "--cached", "--name-only")

    real_text = (
        ROOT / "src/simfleet_edg/evaluation/trip_count_cal_real.py"
    ).read_text(encoding="utf-8")

    checks = {
        "head_exact_parent": git("rev-parse", "HEAD") == PARENT,
        "branch_main": git("branch", "--show-current") == "main",
        "ahead_zero": git("rev-list", "--count", "origin/main..HEAD") == "0",
        "behind_zero": git("rev-list", "--count", "HEAD..origin/main") == "0",
        "no_staged_changes": staged == "",
        "overlay_scope_exact": scope == expected_scope,
        "participation_rows_460": (
            cfg["cal_input"]["expected_participation_rows"] == 460
        ),
        "observed_tripday_rows_399": (
            cfg["cal_input"]["expected_observed_tripday_rows"] == 399
        ),
        "known_notrip_rows_61": (
            cfg["cal_input"]["expected_known_notrip_rows"] == 61
        ),
        "isolated_rows_381": cfg["cal_input"]["expected_isolated_rows"] == 381,
        "count_unobserved_18": (
            cfg["cal_input"]["expected_count_target_unobserved_tripday_rows"] == 18
        ),
        "guardrail_rows_442": (
            cfg["cal_input"]["expected_count_guardrail_person_days"] == 442
        ),
        "subset_not_equality": (
            "if not count_context_ids <= mobile_context_ids:" in real_text
            and "mobile_context_ids != count_context_ids" not in real_text
        ),
        "no_zero_coercion_for_missing_mobile": (
            "Count-unobserved TripDay leaked" in real_text
        ),
        "candidate_metrics_not_seen_before_remediation": (
            rem["trigger"]["candidate_metrics_produced"] is False
        ),
        "candidate_selection_none": (
            rem["trigger"]["candidate_selection"] == "NONE"
        ),
        "old_authorization_invalidated": (
            rem["authorization"][
                "previous_f3_4c2b_authorization_valid_for_retry"
            ]
            is False
        ),
        "new_authorization_required": (
            rem["authorization"][
                "new_authorization_required_after_remediation_commit"
            ]
            is True
        ),
        "test_still_sealed": (
            rem["unchanged_science"]["test_open_authorized"] is False
        ),
        "formal_g2_not_evaluated": (
            rem["unchanged_science"]["formal_g2"] == "NOT_EVALUATED"
        ),
    }

    failed = [name for name, value in checks.items() if not value]
    result = {
        "phase": "F3.4c-2b-R1",
        "status": "PASS" if not failed else "FAIL",
        "remediation_gate": "PASS" if not failed else "FAIL",
        "candidate_selection": "NONE",
        "count_guardrail_person_days": 442,
        "new_real_cal_authorization_required": True,
        "test_open_authorized": False,
        "formal_g2": "NOT_EVALUATED",
        "checks": checks,
        "failed": failed,
        "overlay_scope": {
            "expected_count": len(expected_scope),
            "actual_count": len(scope),
            "missing": sorted(expected_scope - scope),
            "unexpected": sorted(scope - expected_scope),
        },
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
