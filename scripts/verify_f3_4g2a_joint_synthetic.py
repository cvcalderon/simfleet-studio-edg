from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def verify_checksums(run: Path) -> bool:
    manifest = run / "checksums.sha256"
    if not manifest.is_file():
        return False
    for line in manifest.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        expected, name = line.split(maxsplit=1)
        path = run / name.strip()
        if not path.is_file() or sha256_file(path) != expected:
            return False
    return True


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", required=True)
    args = parser.parse_args()

    run = Path(args.run_dir).expanduser().resolve()
    manifest = json.loads((run / "run_manifest.json").read_text(encoding="utf-8"))
    artifacts = pd.read_csv(run / "pipeline_artifact_validation.csv")
    cohort = pd.read_csv(run / "synthetic_person_day_context.csv")
    seeds = pd.read_csv(run / "seed_schedule.csv")
    days = pd.read_csv(run / "synthetic_generated_days.csv")
    trips = pd.read_csv(run / "synthetic_generated_trips.csv")
    summary = pd.read_csv(run / "synthetic_pipeline_summary.csv")
    metrics = pd.read_csv(run / "synthetic_metric_smoke.csv")
    validation = pd.read_csv(run / "validation.csv")
    issues = pd.read_csv(run / "issues.csv")

    pipelines = set(days["pipeline"].astype(str))
    trip_pipelines = set(trips["pipeline"].astype(str))
    distance_valid = (
        len(trips) > 0
        and np.isfinite(trips["distance_prior_km"].astype(float)).all()
        and (trips["distance_prior_km"].astype(float) > 0).all()
    )

    checks = {
        "status_pass": manifest["status"] == "PASS",
        "phase_exact": manifest["phase"] == "F3.4g-2a",
        "mode_synthetic": manifest["mode"] == "SYNTHETIC_PREOPEN",
        "checksums_ok": verify_checksums(run),
        "artifact_slots_10": len(artifacts) == 10,
        "artifact_validation_all_pass": artifacts["status"].eq("PASS").all(),
        "synthetic_person_days_8": len(cohort) == 8,
        "seed_rows_32": len(seeds) == 32,
        "generated_day_rows_512": len(days) == 512,
        "both_pipelines_in_days": pipelines == {"SELECTED", "ALL_REFERENCE"},
        "both_pipelines_generate_trips": trip_pipelines == {"SELECTED", "ALL_REFERENCE"},
        "summary_rows_2": len(summary) == 2,
        "summary_nondecision": not summary["decision_authorized"].astype(str).str.lower().eq("true").any(),
        "metric_rows_3": len(metrics) == 3,
        "metrics_nondecision": not metrics["decision_authorized"].astype(str).str.lower().eq("true").any(),
        "generated_distance_positive_finite": bool(distance_valid),
        "validation_all_pass": validation["status"].eq("PASS").all(),
        "issues_empty": len(issues) == 0,
        "hard_violations_zero": int(manifest["hard_invariant_violations"]) == 0,
        "cal_files_empty": manifest["cal_files_read"] == [],
        "cal_rows_zero": int(manifest["cal_rows_read"]) == 0,
        "candidate_selection_none": manifest["candidate_selection"] == "NONE",
        "joint_real_cal_closed": manifest["joint_real_cal_open_authorized"] is False,
        "joint_not_evaluated": manifest["joint_gate_evaluated"] is False,
        "test_files_empty": manifest["test_files_read"] == [],
        "test_rows_zero": int(manifest["test_rows_read"]) == 0,
        "test_sealed": manifest["test_open_authorized"] is False,
        "g2_not_evaluated": manifest["formal_g2"] == "NOT_EVALUATED",
    }

    failed = [name for name, value in checks.items() if not bool(value)]
    payload = {
        "phase": "F3.4g-2a",
        "component": "DGEN_JOINT_PIPELINE",
        "mode": "SYNTHETIC_PREOPEN",
        "status": "PASS" if not failed else "FAIL",
        "runbundle_gate": "PASS" if not failed else "FAIL",
        "pipeline_artifact_slots": len(artifacts),
        "synthetic_person_days": len(cohort),
        "stochastic_replicates": len(seeds),
        "generated_day_rows": len(days),
        "generated_trip_rows": len(trips),
        "cal_rows_read": int(manifest["cal_rows_read"]),
        "candidate_selection": manifest["candidate_selection"],
        "joint_real_cal_open_authorized": False,
        "joint_gate_evaluated": False,
        "test_rows_read": int(manifest["test_rows_read"]),
        "formal_g2": manifest["formal_g2"],
        "checks": {name: bool(value) for name, value in checks.items()},
        "failed": failed,
    }
    print(json.dumps(payload, indent=2, sort_keys=True))
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
