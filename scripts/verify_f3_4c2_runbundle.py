from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import pandas as pd

REQUIRED = {
    "run_manifest.json",
    "execution_contract_snapshot.yaml",
    "execution_authorization_snapshot.json",
    "environment.json",
    "cal_access_manifest.json",
    "input_hash_validation.csv",
    "candidate_artifact_validation.csv",
    "primary_metrics.csv",
    "isolated_guardrail_candidate_metrics.csv",
    "isolated_conditional_guardrails.csv",
    "isolated_guardrails.csv",
    "bootstrap_intervals.csv",
    "grid_selection.csv",
    "promotion_decisions.csv",
    "propagated_guardrail_candidate_metrics.csv",
    "propagated_conditional_guardrails.csv",
    "propagated_guardrails.csv",
    "upstream_selection_snapshot.json",
    "selected_component_artifact.json",
    "stochastic_evidence.csv.gz",
    "evidence_manifest.json",
    "validation.csv",
    "performance.json",
    "issues.csv",
    "checksums.sha256",
}

PROMOTION_COLUMNS = [
    "incumbent_artifact_id",
    "challenger_artifact_id",
    "point_improvement",
    "practical_margin",
    "bootstrap_ci_lower",
    "bootstrap_ci_upper",
    "promoted",
    "reasons",
    "stage",
]

BOOTSTRAP_COLUMNS = [
    "incumbent_artifact_id",
    "challenger_artifact_id",
    "bootstrap_replicates",
    "ci_lower",
    "ci_median",
    "ci_upper",
]


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def checksums_ok(run_dir: Path) -> bool:
    for line in (run_dir / "checksums.sha256").read_text().splitlines():
        if not line.strip():
            continue
        digest, name = line.split(maxsplit=1)
        if sha256(run_dir / name.strip()) != digest:
            return False
    return True


def read_csv_allow_empty(path: Path, columns: list[str]) -> pd.DataFrame:
    try:
        return pd.read_csv(path)
    except pd.errors.EmptyDataError:
        return pd.DataFrame(columns=columns)


def expected_decision_rows(grid: pd.DataFrame) -> int:
    if "selected_within_family" not in grid.columns:
        raise ValueError("grid_selection.csv lacks selected_within_family")
    selected = grid["selected_within_family"].astype(str).str.lower() == "true"
    return int(selected.sum())


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", type=Path, required=True)
    args = parser.parse_args()
    run = args.run_dir

    manifest = json.loads((run / "run_manifest.json").read_text())
    selected = json.loads((run / "selected_component_artifact.json").read_text())
    upstream = json.loads((run / "upstream_selection_snapshot.json").read_text())
    validation = pd.read_csv(run / "validation.csv")
    primary = pd.read_csv(run / "primary_metrics.csv")
    grid = pd.read_csv(run / "grid_selection.csv")
    promotions = read_csv_allow_empty(
        run / "promotion_decisions.csv",
        PROMOTION_COLUMNS,
    )
    bootstraps = read_csv_allow_empty(
        run / "bootstrap_intervals.csv",
        BOOTSTRAP_COLUMNS,
    )
    propagated = pd.read_csv(run / "propagated_guardrails.csv")

    expected_decisions = expected_decision_rows(grid)
    proposal = manifest.get("proposed_selected_artifact_id")
    selected_status = selected.get("status")

    checks = {
        "required_files_exact_or_superset": REQUIRED <= {p.name for p in run.iterdir()},
        "checksums_ok": checksums_ok(run),
        "status_pass": manifest.get("status") == "PASS",
        "component_trip_count": manifest.get("component") == "DG_TRIP_COUNT",
        "candidate_artifacts_5": manifest.get("candidate_artifacts") == 5,
        "cal_physical_rows_1310": manifest.get("cal_rows_read_total_physical") == 1310,
        "isolated_rows_381": manifest.get("cal_isolated_evaluation_rows") == 381,
        "participation_rows_460": manifest.get("cal_participation_rows") == 460,
        "observed_tripday_rows_399": manifest.get("cal_observed_tripday_rows") == 399,
        "known_notrip_rows_61": manifest.get("cal_known_notrip_rows") == 61,
        "count_target_observed_tripday_rows_381": manifest.get(
            "cal_count_target_observed_tripday_rows"
        )
        == 381,
        "count_target_unobserved_tripday_rows_18": manifest.get(
            "cal_count_target_unobserved_tripday_rows"
        )
        == 18,
        "count_guardrail_person_days_442": manifest.get(
            "cal_count_guardrail_person_days"
        )
        == 442,
        "primary_metrics_5": len(primary) == 5,
        "grid_candidates_4": len(grid) == 4,
        "decision_rows_match_eligible_family_winners": (
            len(promotions) == expected_decisions
        ),
        "bootstrap_rows_match_decision_rows": len(bootstraps) == len(promotions),
        "zero_decisions_valid_when_no_family_winner": (
            expected_decisions != 0
            or (promotions.empty and bootstraps.empty)
        ),
        "propagated_guardrail_one": len(propagated) == 1,
        "upstream_pa1": upstream.get("artifact_id")
        == "DG_PARTICIPATION::PART_A::PA1",
        "selection_proposal_present_or_explicitly_blocked": (
            proposal is not None
            or selected_status == "BLOCKED_PROPAGATED_GUARDRAIL_RETURN_TO_MAIN"
        ),
        "selection_proposal_not_main_frozen": selected.get(
            "authorized_for_downstream"
        )
        is False,
        "next_component_not_authorized": manifest.get(
            "next_component_authorized"
        )
        is False,
        "test_rows_zero": manifest.get("test_rows_read") == 0,
        "test_not_authorized": manifest.get("test_open_authorized") is False,
        "formal_g2_not_evaluated": manifest.get("formal_g2") == "NOT_EVALUATED",
        "validation_all_pass": set(validation["status"]) == {"PASS"},
    }
    failed = [name for name, value in checks.items() if not value]
    result = {
        "phase": "F3.4c-2b",
        "status": "PASS" if not failed else "FAIL",
        "runbundle_gate": "PASS" if not failed else "FAIL",
        "proposed_selected_artifact_id": proposal,
        "candidate_selection_state": manifest.get("candidate_selection_state"),
        "eligible_family_winners": expected_decisions,
        "promotion_decision_rows": len(promotions),
        "bootstrap_rows": len(bootstraps),
        "propagated_guardrails_pass": manifest.get(
            "propagated_guardrails_pass"
        ),
        "next_component_authorized": False,
        "test_open_authorized": False,
        "formal_g2": "NOT_EVALUATED",
        "checks": checks,
        "failed": failed,
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
