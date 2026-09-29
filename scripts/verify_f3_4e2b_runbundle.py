from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import pandas as pd

REQUIRED = {
    "run_manifest.json",
    "execution_authorization_snapshot.json",
    "execution_contract_snapshot.yaml",
    "cal_access_manifest.json",
    "input_hash_validation.csv",
    "candidate_artifact_validation.csv",
    "primary_metrics.csv",
    "isolated_auxiliary_metrics.csv",
    "isolated_temporal_guardrails.csv",
    "bootstrap_intervals.csv",
    "grid_selection.csv",
    "promotion_decisions.csv",
    "propagated_temporal_guardrails.csv",
    "upstream_selection_snapshot.json",
    "selected_component_artifact.json",
    "validation.csv",
    "issues.csv",
    "performance.json",
    "environment.json",
    "evidence_manifest.json",
    "checksums.sha256",
}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def checksums_ok(run_dir: Path) -> bool:
    for line in (run_dir / "checksums.sha256").read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        expected, name = line.split(maxsplit=1)
        if sha256(run_dir / name.strip()) != expected:
            return False
    return True


def csv(path: Path) -> pd.DataFrame:
    if path.stat().st_size == 0:
        return pd.DataFrame()
    try:
        return pd.read_csv(path)
    except pd.errors.EmptyDataError:
        return pd.DataFrame()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", type=Path, required=True)
    args = parser.parse_args()
    run = args.run_dir.expanduser().resolve()
    files = {p.name for p in run.iterdir() if p.is_file()}
    manifest = json.loads((run / "run_manifest.json").read_text(encoding="utf-8"))
    auth = json.loads((run / "execution_authorization_snapshot.json").read_text(encoding="utf-8"))
    access = json.loads((run / "cal_access_manifest.json").read_text(encoding="utf-8"))
    selected = json.loads((run / "selected_component_artifact.json").read_text(encoding="utf-8"))
    upstream = json.loads((run / "upstream_selection_snapshot.json").read_text(encoding="utf-8"))
    primary = csv(run / "primary_metrics.csv")
    hard = csv(run / "isolated_temporal_guardrails.csv")
    grid = csv(run / "grid_selection.csv")
    promotion = csv(run / "promotion_decisions.csv")
    bootstrap = csv(run / "bootstrap_intervals.csv")
    propagated = csv(run / "propagated_temporal_guardrails.csv")
    validation = csv(run / "validation.csv")
    checks = {
        "required_files_exact_or_superset": REQUIRED <= files,
        "checksums_ok": checksums_ok(run),
        "status_pass": manifest.get("status") == "PASS",
        "component_time_schedule": manifest.get("component") == "DG_TIME_SCHEDULE",
        "candidate_artifacts_7": manifest.get("candidate_artifacts") == 7,
        "primary_metrics_7": len(primary) == 7,
        "hard_rows_7": len(hard) == 7,
        "grid_candidates_6": len(grid) == 6,
        "decision_rows_le_2": len(promotion) <= 2,
        "bootstrap_rows_match_decision_rows": len(bootstrap) == len(promotion),
        "cal_physical_rows_1712": access.get("cal_rows_read_total_physical") == 1712,
        "fixed_cohort_days_378": access.get("cal_fixed_source_cohort_days") == 378,
        "isolated_rows_1243": access.get("cal_isolated_time_rows") == 1243,
        "isolated_reference_hard_pass": bool(hard.loc[hard["artifact_id"].eq("TIME_REF_REFERENCE"), "hard_pass"].astype(bool).all()),
        "propagated_rows_one_or_two": 1 <= len(propagated) <= 2,
        "propagated_all_hard_pass_if_proposed": (bool(propagated["hard_pass"].astype(bool).all()) if selected.get("proposed_selected_artifact_id") else True),
        "selection_proposal_present_or_explicitly_blocked": selected.get("status") in {
            "PROPOSED_BY_FROZEN_CAL_RULES_AWAITING_MAIN_FREEZE",
            "BLOCKED_PROPAGATED_TEMPORAL_GUARDRAIL_RETURN_TO_MAIN",
        },
        "authorization_bound_to_implementation": auth.get("authorized_implementation_commit") == manifest.get("implementation_commit"),
        "authorization_real_cal_true": auth.get("real_time_schedule_cal_open_authorized") is True,
        "authorization_files_exact": set(auth.get("allowed_cal_files", [])) == {"person_day_context.csv", "time_trips.csv"},
        "distance_not_authorized": auth.get("distance_prior_real_cal_authorized") is False and manifest.get("distance_prior_real_cal_authorized") is False,
        "test_sealed": auth.get("test_open_authorized") is False and manifest.get("test_open_authorized") is False,
        "test_rows_zero": manifest.get("test_rows_read") == 0,
        "g2_not_evaluated": manifest.get("formal_g2") == "NOT_EVALUATED",
        "upstream_pa1": upstream.get("participation_artifact_id") == "DG_PARTICIPATION::PART_A::PA1",
        "upstream_count_ref": upstream.get("trip_count_artifact_id") == "DG_TRIP_COUNT::COUNT_REF::REFERENCE",
        "upstream_cha2": upstream.get("activity_chain_artifact_id") == "DG_ACTIVITY_CHAIN::CHAIN_A::CHA2",
        "validation_all_pass": bool(validation["status"].eq("PASS").all()),
        "downstream_not_authorized": selected.get("distance_prior_real_cal_authorized") is False and selected.get("authorized_for_downstream") is False,
    }
    checks = {k: bool(v) for k, v in checks.items()}
    failed = [k for k, v in checks.items() if not v]
    payload = {
        "phase": "F3.4e-2b",
        "component": "DG_TIME_SCHEDULE",
        "status": "PASS" if not failed else "FAIL",
        "runbundle_gate": "PASS" if not failed else "FAIL",
        "checks": checks,
        "failed": failed,
        "candidate_selection_state": manifest.get("candidate_selection_state"),
        "proposed_selected_artifact_id": manifest.get("proposed_selected_artifact_id"),
        "promotion_decision_rows": len(promotion),
        "bootstrap_rows": len(bootstrap),
        "propagated_temporal_guardrail_pass": manifest.get("propagated_temporal_guardrail_pass"),
        "distance_prior_real_cal_authorized": False,
        "test_open_authorized": False,
        "formal_g2": "NOT_EVALUATED",
    }
    print(json.dumps(payload, indent=2, sort_keys=True))
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
