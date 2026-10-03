from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import pandas as pd


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def verify_recursive_checksums(run: Path) -> bool:
    manifest = run / "checksums.sha256"
    if not manifest.is_file():
        return False
    for line in manifest.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        expected, rel = line.split(maxsplit=1)
        path = run / rel.strip()
        if not path.is_file() or sha256_file(path) != expected:
            return False
    return True


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", required=True)
    args = parser.parse_args()

    run = Path(args.run_dir).expanduser().resolve()
    manifest = json.loads(
        (run / "run_manifest.json").read_text(encoding="utf-8")
    )
    consumption = json.loads(
        (run / "holdout_consumption.json").read_text(encoding="utf-8")
    )
    materialization = json.loads(
        (run / "test_materialization_manifest.json").read_text(
            encoding="utf-8"
        )
    )
    g2 = json.loads(
        (run / "g2_decision.json").read_text(encoding="utf-8")
    )
    source_validation = pd.read_csv(run / "source_hash_validation.csv")
    artifacts = pd.read_csv(run / "pipeline_artifact_validation.csv")
    metrics = pd.read_csv(run / "test_metrics.csv")
    validation = pd.read_csv(run / "validation.csv")
    issues = pd.read_csv(run / "issues.csv")
    materialized_dir = run / "materialized_test"

    decision = metrics.loc[metrics["decision_role"].ne("REPORT_ONLY")]
    report = metrics.loc[metrics["decision_role"].eq("REPORT_ONLY")]
    expected_tables = {
        "person_day_context.csv",
        "participation.csv",
        "trip_count.csv",
        "chain_days.csv",
        "chain_transitions.csv",
        "time_trips.csv",
        "distance_raw.csv",
        "distance_expanded_sensitivity.csv",
    }
    actual_tables = {
        path.name
        for path in materialized_dir.glob("*.csv")
        if path.is_file()
    }

    checks = {
        "execution_status_pass": manifest["status"] == "PASS",
        "phase_exact": manifest["phase"] == "F3.4g-2f",
        "mode_test": manifest["mode"] == "CONTROLLED_HELDOUT_TEST",
        "recursive_checksums_pass": verify_recursive_checksums(run),
        "holdout_consumed": consumption["holdout_consumed"] is True,
        "same_holdout_rerun_forbidden": (
            manifest["same_holdout_rerun_authorized"] is False
        ),
        "post_test_tuning_forbidden": (
            manifest["post_test_tuning_authorized"] is False
        ),
        "strict_test_households_260": (
            manifest["strict_test_households"] == 260
        ),
        "eight_materialized_tables": actual_tables == expected_tables,
        "materialization_hashes_8": len(materialization["table_sha256"]) == 8,
        "source_hash_validation_13_pass": (
            len(source_validation) == 13
            and source_validation["status"].eq("PASS").all()
        ),
        "artifact_slots_10": len(artifacts) == 10,
        "artifact_validation_pass": artifacts["status"].eq("PASS").all(),
        "metrics_17": len(metrics) == 17,
        "decision_metrics_14": len(decision) == 14,
        "report_only_3": len(report) == 3,
        "g2_is_pass_or_fail": g2["formal_g2"] in {"PASS", "FAIL"},
        "g2_matches_manifest": manifest["formal_g2"] == g2["formal_g2"],
        "validation_all_pass": validation["status"].eq("PASS").all(),
        "issues_empty": len(issues) == 0,
        "candidate_selection_none": manifest["candidate_selection"] == "NONE",
    }

    failed = [name for name, value in checks.items() if not bool(value)]
    payload = {
        "phase": "F3.4g-2f",
        "component": "DGEN_JOINT_PIPELINE",
        "status": "PASS" if not failed else "FAIL",
        "runbundle_gate": "PASS" if not failed else "FAIL",
        "execution_status": manifest["status"],
        "formal_g2": manifest["formal_g2"],
        "decision_metrics_pass": g2["decision_metrics_pass"],
        "decision_metrics_total": g2["decision_metrics_total"],
        "report_only_metrics": g2["report_only_metrics"],
        "strict_test_households": manifest["strict_test_households"],
        "materialized_test_row_counts": manifest[
            "materialized_test_row_counts"
        ],
        "generated_day_rows": manifest["generated_day_rows"],
        "generated_trip_rows": manifest["generated_trip_rows"],
        "holdout_consumed": True,
        "same_holdout_rerun_authorized": False,
        "post_test_tuning_authorized": False,
        "checks": {name: bool(value) for name, value in checks.items()},
        "failed": failed,
    }
    print(json.dumps(payload, indent=2, sort_keys=True))
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
