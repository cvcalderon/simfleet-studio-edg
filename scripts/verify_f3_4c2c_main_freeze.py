from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path

import pandas as pd
import yaml

ROOT = Path.cwd()
PARENT = "2d55e7fd28611f529c91741476cb55bdb2b79c9e"
RUN_IMPL = "372a6c03739f71b68c65c15c546a515f09830435"
SELECTED = "DG_TRIP_COUNT::COUNT_REF::REFERENCE"
FILELIST = ROOT / "docs/F3_4C2C_OVERLAY_FILELIST_v1.txt"
WITNESS = ROOT / "docs/F3_4C2C_A2_RUN_WITNESS_v1.json"


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], text=True).rstrip("\n")


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def checksums_ok(run: Path) -> bool:
    for line in (run / "checksums.sha256").read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        digest, rel = line.split(maxsplit=1)
        if sha256(run / rel.strip()) != digest:
            return False
    return True


def read_csv_allow_empty(path: Path) -> pd.DataFrame:
    try:
        return pd.read_csv(path)
    except pd.errors.EmptyDataError:
        return pd.DataFrame()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", type=Path, required=True)
    args = parser.parse_args()
    run = args.run_dir.resolve()

    cfg = yaml.safe_load(
        (ROOT / "configs/f3/f3_4c2c_trip_count_main_freeze_v1.yaml")
        .read_text(encoding="utf-8")
    )
    witness = json.loads(WITNESS.read_text(encoding="utf-8"))
    manifest = json.loads((run / "run_manifest.json").read_text(encoding="utf-8"))
    selected = json.loads(
        (run / "selected_component_artifact.json").read_text(encoding="utf-8")
    )
    primary = pd.read_csv(run / "primary_metrics.csv")
    grid = pd.read_csv(run / "grid_selection.csv")
    promotions = read_csv_allow_empty(run / "promotion_decisions.csv")
    bootstraps = read_csv_allow_empty(run / "bootstrap_intervals.csv")
    isolated = pd.read_csv(run / "isolated_guardrails.csv")
    propagated = pd.read_csv(run / "propagated_guardrails.csv")

    status_lines = [line for line in git("status", "--porcelain").splitlines() if line]
    scope = {line[3:] for line in status_lines}
    expected_scope = {
        line.strip()
        for line in FILELIST.read_text(encoding="utf-8").splitlines()
        if line.strip()
    }
    staged = git("diff", "--cached", "--name-only")

    primary_ref = float(
        primary.loc[primary["artifact_id"] == SELECTED, "value"].iloc[0]
    )
    primary_min_artifact = primary.sort_values("value").iloc[0]["artifact_id"]
    all_challenger_guardrails_fail = (
        len(isolated) == 4
        and not isolated["guardrails_pass"].astype(bool).any()
    )
    propagated_self_check = (
        len(propagated) == 1
        and propagated.iloc[0]["incumbent_artifact_id"] == SELECTED
        and propagated.iloc[0]["challenger_artifact_id"] == SELECTED
        and bool(propagated.iloc[0]["guardrails_pass"])
    )

    expected_hashes = witness["file_sha256"]
    witness_hashes_match = all(
        sha256(run / name) == digest
        for name, digest in expected_hashes.items()
    )

    checks = {
        "head_exact_parent": git("rev-parse", "HEAD") == PARENT,
        "branch_main": git("branch", "--show-current") == "main",
        "ahead_zero": git("rev-list", "--count", "origin/main..HEAD") == "0",
        "behind_zero": git("rev-list", "--count", "HEAD..origin/main") == "0",
        "no_staged_changes": staged == "",
        "overlay_scope_exact": scope == expected_scope,
        "runbundle_checksums_pass": checksums_ok(run),
        "witness_hashes_match_runbundle": witness_hashes_match,
        "run_status_pass": manifest.get("status") == "PASS",
        "run_implementation_exact": manifest.get("implementation_commit") == RUN_IMPL,
        "component_trip_count": manifest.get("component") == "DG_TRIP_COUNT",
        "candidate_artifacts_5": manifest.get("candidate_artifacts") == 5,
        "proposal_reference": manifest.get("proposed_selected_artifact_id") == SELECTED,
        "proposal_awaiting_main_freeze": manifest.get("candidate_selection_state")
        == "PROPOSED_BY_FROZEN_CAL_RULES_AWAITING_MAIN_FREEZE",
        "source_selected_not_downstream_authorized": selected.get(
            "authorized_for_downstream"
        )
        is False,
        "reference_primary_value_exact": abs(
            primary_ref - 0.8931199056452576
        )
        < 1e-15,
        "reference_is_primary_minimum": primary_min_artifact == SELECTED,
        "grid_candidates_4": len(grid) == 4,
        "eligible_family_winners_zero": int(
            grid["selected_within_family"]
            .astype(str)
            .str.lower()
            .eq("true")
            .sum()
        )
        == 0,
        "all_challengers_fail_isolated_guardrails": all_challenger_guardrails_fail,
        "promotion_rows_zero": len(promotions) == 0,
        "bootstrap_rows_zero": len(bootstraps) == 0,
        "propagated_reference_self_check_pass": propagated_self_check,
        "cal_physical_1310": manifest.get("cal_rows_read_total_physical") == 1310,
        "participation_460": manifest.get("cal_participation_rows") == 460,
        "tripday_399": manifest.get("cal_observed_tripday_rows") == 399,
        "notrip_61": manifest.get("cal_known_notrip_rows") == 61,
        "isolated_381": manifest.get("cal_isolated_evaluation_rows") == 381,
        "count_observed_381": manifest.get(
            "cal_count_target_observed_tripday_rows"
        )
        == 381,
        "count_unobserved_18": manifest.get(
            "cal_count_target_unobserved_tripday_rows"
        )
        == 18,
        "guardrail_days_442": manifest.get(
            "cal_count_guardrail_person_days"
        )
        == 442,
        "freeze_artifact_exact": cfg["selection"]["artifact_id"] == SELECTED,
        "freeze_target_main_frozen": cfg["selection"]["target_state_after_commit"]
        == "MAIN_FROZEN",
        "freeze_does_not_authorize_next_execution": cfg["selection"][
            "authorized_for_downstream_component_execution"
        ]
        is False,
        "test_rows_zero": manifest.get("test_rows_read") == 0,
        "test_still_sealed": manifest.get("test_open_authorized") is False,
        "next_component_not_authorized": manifest.get(
            "next_component_authorized"
        )
        is False,
        "formal_g2_not_evaluated": manifest.get("formal_g2") == "NOT_EVALUATED",
    }

    failed = [name for name, value in checks.items() if not value]
    result = {
        "phase": "F3.4c-2c",
        "status": "PASS" if not failed else "FAIL",
        "main_freeze_gate": "PASS" if not failed else "FAIL",
        "selected_artifact_id": SELECTED,
        "target_state_after_commit": "MAIN_FROZEN",
        "cal_reopened": False,
        "test_open_authorized": False,
        "next_component_authorized": False,
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
