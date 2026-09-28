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
    "isolated_guardrail_candidate_metrics.csv",
    "isolated_guardrails.csv",
    "bootstrap_intervals.csv",
    "grid_selection.csv",
    "promotion_decisions.csv",
    "propagated_guardrail_candidate_metrics.csv",
    "propagated_guardrails.csv",
    "upstream_selection_snapshot.json",
    "selected_component_artifact.json",
    "purpose_attribution_snapshot.json",
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
    run_dir = args.run_dir
    files = {path.name for path in run_dir.iterdir() if path.is_file()}
    manifest = json.loads((run_dir / "run_manifest.json").read_text(encoding="utf-8"))
    auth = json.loads(
        (run_dir / "execution_authorization_snapshot.json").read_text(encoding="utf-8")
    )
    access = json.loads((run_dir / "cal_access_manifest.json").read_text(encoding="utf-8"))
    selected = json.loads(
        (run_dir / "selected_component_artifact.json").read_text(encoding="utf-8")
    )
    purpose = json.loads(
        (run_dir / "purpose_attribution_snapshot.json").read_text(encoding="utf-8")
    )
    primary = csv(run_dir / "primary_metrics.csv")
    grid = csv(run_dir / "grid_selection.csv")
    promotion = csv(run_dir / "promotion_decisions.csv")
    bootstrap = csv(run_dir / "bootstrap_intervals.csv")
    propagated = csv(run_dir / "propagated_guardrails.csv")
    validation = csv(run_dir / "validation.csv")
    checks = {
        "required_files_exact_or_superset": REQUIRED <= files,
        "checksums_ok": checksums_ok(run_dir),
        "status_pass": manifest.get("status") == "PASS",
        "component_activity_chain": manifest.get("component") == "DG_ACTIVITY_CHAIN",
        "candidate_artifacts_6": manifest.get("candidate_artifacts") == 6,
        "primary_metrics_6": len(primary) == 6,
        "grid_candidates_5": len(grid) == 5,
        "decision_rows_le_2": len(promotion) <= 2,
        "bootstrap_rows_match_decision_rows": len(bootstrap) == len(promotion),
        "cal_physical_rows_1853": access.get("cal_rows_read_total_physical") == 1853,
        "fixed_cohort_days_319": access.get("cal_fixed_source_cohort_days") == 319,
        "isolated_rows_1065": access.get("cal_isolated_transition_rows") == 1065,
        "propagated_guardrail_one": len(propagated) == 1,
        "selection_proposal_present_or_explicitly_blocked": selected.get("status") in {
            "PROPOSED_BY_FROZEN_CAL_RULES_AWAITING_MAIN_FREEZE",
            "BLOCKED_PROPAGATED_GUARDRAIL_RETURN_TO_MAIN",
        },
        "selection_not_main_frozen": selected.get("authorized_for_downstream") is False,
        "next_component_not_authorized": manifest.get("next_component_authorized") is False,
        "test_not_authorized": manifest.get("test_open_authorized") is False,
        "test_rows_zero": manifest.get("test_rows_read") == 0,
        "formal_g2_not_evaluated": manifest.get("formal_g2") == "NOT_EVALUATED",
        "auth_commit_matches_run": auth.get("authorized_implementation_commit") == manifest.get("implementation_commit"),
        "auth_real_cal_true": auth.get("real_activity_chain_cal_open_authorized") is True,
        "purpose_primitive_exact": purpose.get("primitive_id") == "CHAIN_PURPOSE_ATTRIBUTION_V1",
        "purpose_hash_exact": purpose.get("artifact_sha256") == "ab42cf42c9568ef4f085f071299fc941d421c42337f353e00870cd05c94f94fb",
        "validation_all_pass": bool(not validation.empty and validation["status"].eq("PASS").all()),
    }
    failed = [key for key, value in checks.items() if not value]
    payload = {
        "phase": "F3.4d-2b",
        "component": "DG_ACTIVITY_CHAIN",
        "status": "PASS" if not failed else "FAIL",
        "runbundle_gate": "PASS" if not failed else "FAIL",
        "checks": checks,
        "failed": failed,
        "candidate_selection_state": manifest.get("candidate_selection_state"),
        "proposed_selected_artifact_id": manifest.get("proposed_selected_artifact_id"),
        "promotion_decision_rows": len(promotion),
        "bootstrap_rows": len(bootstrap),
        "propagated_guardrails_pass": manifest.get("propagated_guardrails_pass"),
        "test_open_authorized": False,
        "next_component_authorized": False,
        "formal_g2": "NOT_EVALUATED",
    }
    print(json.dumps(payload, indent=2, sort_keys=True))
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
