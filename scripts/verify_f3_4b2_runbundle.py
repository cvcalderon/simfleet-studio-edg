from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import pandas as pd

REQUIRED_FILES = {
    "run_manifest.json",
    "execution_contract_snapshot.yaml",
    "execution_authorization_snapshot.json",
    "environment.json",
    "cal_access_manifest.json",
    "input_hash_validation.csv",
    "candidate_artifact_validation.csv",
    "candidate_probabilities.csv",
    "primary_metrics.csv",
    "guardrail_candidate_metrics.csv",
    "conditional_guardrails.csv",
    "guardrails.csv",
    "bootstrap_intervals.csv",
    "grid_selection.csv",
    "promotion_decisions.csv",
    "validation.csv",
    "performance.json",
    "issues.csv",
    "part_b_calibration_decision.json",
    "selected_component_artifact.json",
    "evidence_manifest.json",
    "stochastic_evidence.csv.gz",
    "checksums.sha256",
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def checksums_ok(run_dir: Path) -> bool:
    for line in (run_dir / "checksums.sha256").read_text().splitlines():
        if not line.strip():
            continue
        digest, name = line.split(maxsplit=1)
        if sha256(run_dir / name.strip()) != digest:
            return False
    return True


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", type=Path, required=True)
    args = parser.parse_args()
    run_dir = args.run_dir
    manifest = json.loads((run_dir / "run_manifest.json").read_text())
    access = json.loads((run_dir / "cal_access_manifest.json").read_text())
    selected = json.loads(
        (run_dir / "selected_component_artifact.json").read_text()
    )
    validation = pd.read_csv(run_dir / "validation.csv")
    artifact_validation = pd.read_csv(
        run_dir / "candidate_artifact_validation.csv"
    )
    primary = pd.read_csv(run_dir / "primary_metrics.csv")
    evidence = json.loads((run_dir / "evidence_manifest.json").read_text())
    names = {path.name for path in run_dir.iterdir() if path.is_file()}
    cal_names = {Path(path).name for path in access.get("cal_files_opened", [])}
    checks = {
        "required_files_exact_or_superset": REQUIRED_FILES.issubset(names),
        "checksums_ok": checksums_ok(run_dir),
        "status_pass": manifest.get("status") == "PASS",
        "component_participation": manifest.get("component") == "DG_PARTICIPATION",
        "candidate_artifacts_8": (
            manifest.get("candidate_artifacts") == 8
            and len(primary) == 8
            and len(artifact_validation) == 8
        ),
        "cal_files_exact_two": cal_names
        == {"person_day_context.csv", "participation.csv"},
        "cal_physical_rows_929": (
            access.get("cal_rows_read_total_physical") == 929
        ),
        "cal_evaluation_rows_460": access.get("cal_evaluation_rows") == 460,
        "test_rows_zero": (
            access.get("test_rows_read") == 0
            and manifest.get("test_rows_read") == 0
        ),
        "test_files_none": access.get("test_files_opened") == [],
        "selection_proposal_not_frozen": (
            manifest.get("candidate_selection_state")
            == "PROPOSED_BY_FROZEN_RULES_AWAITING_MAIN_FREEZE"
            and selected.get("authorized_for_downstream") is False
        ),
        "next_component_not_authorized": (
            manifest.get("next_component_authorized") is False
            and selected.get("next_component_authorized") is False
        ),
        "validation_all_pass": set(validation["status"]) == {"PASS"},
        "artifact_validation_all_pass": (
            set(artifact_validation["status"]) == {"PASS"}
        ),
        "stochastic_evidence_rows_exact": (
            evidence.get("rows") == 8 * 32 * 460
        ),
        "formal_g2_not_evaluated": (
            manifest.get("formal_g2") == "NOT_EVALUATED"
        ),
        "test_not_authorized": manifest.get("test_open_authorized") is False,
    }
    failed = [name for name, value in checks.items() if not value]
    result = {
        "phase": "F3.4b-2b",
        "status": "PASS" if not failed else "FAIL",
        "runbundle_gate": "PASS" if not failed else "FAIL",
        "checks": checks,
        "failed": failed,
        "proposed_selected_artifact_id": manifest.get(
            "proposed_selected_artifact_id"
        ),
        "next_component_authorized": False,
        "test_open_authorized": False,
        "formal_g2": "NOT_EVALUATED",
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
