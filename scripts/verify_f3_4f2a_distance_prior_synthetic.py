from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def verify_checksums(run: Path) -> bool:
    manifest = run / "checksums.sha256"
    if not manifest.is_file():
        return False
    for line in manifest.read_text(encoding="utf-8").splitlines():
        if not line:
            continue
        digest, rel = line.split(maxsplit=1)
        if sha(run / rel) != digest:
            return False
    return True


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", type=Path, required=True)
    args = parser.parse_args()
    run = args.run_dir.expanduser().resolve()

    manifest = json.loads((run / "run_manifest.json").read_text(encoding="utf-8"))
    artifacts = pd.read_csv(run / "artifact_validation.csv")
    primary = pd.read_csv(run / "synthetic_primary_metrics.csv")
    summary = pd.read_csv(run / "synthetic_summary_metrics.csv")
    draws = pd.read_csv(run / "synthetic_generated_draws.csv")
    seeds = pd.read_csv(run / "seed_schedule.csv")
    validation = pd.read_csv(run / "validation.csv")

    values = pd.to_numeric(draws["distance_prior_km"], errors="coerce").to_numpy(dtype=float)
    checks = {
        "checksums_ok": verify_checksums(run),
        "status_pass": manifest["status"] == "PASS",
        "mode_synthetic": manifest["mode"] == "SYNTHETIC_PREOPEN",
        "candidate_artifacts_5": int(manifest["candidate_artifacts"]) == 5 and len(artifacts) == 5,
        "artifact_validation_all_pass": artifacts["status"].eq("PASS").all(),
        "generated_draws_160": int(manifest["generated_draw_rows"]) == 160 and len(draws) == 160,
        "primary_rows_5": int(manifest["synthetic_primary_rows"]) == 5 and len(primary) == 5,
        "summary_rows_20": int(manifest["synthetic_summary_rows"]) == 20 and len(summary) == 20,
        "seed_rows_32": len(seeds) == 32,
        "same_32_seed_schedule_for_all_candidates": draws.groupby("artifact_id")["seed"].apply(tuple).nunique() == 1,
        "generated_distance_positive_finite": np.isfinite(values).all() and (values > 0).all(),
        "generated_hard_violations_zero": int(manifest["generated_hard_invariant_violations"]) == 0,
        "validation_all_pass": validation["status"].eq("PASS").all(),
        "selection_none": manifest["candidate_selection"] == "NONE",
        "synthetic_metrics_not_selection": not primary["selection_authorized"].astype(bool).any(),
        "synthetic_summary_not_decision": not summary["synthetic_decision_authorized"].astype(bool).any(),
        "mean_report_only": set(summary.loc[summary["statistic"] == "MEAN", "role"]) == {"REPORT_ONLY_UNTHRESHOLDED"},
        "cal_files_empty": manifest["cal_files_read"] == [],
        "cal_rows_zero": int(manifest["cal_rows_read"]) == 0,
        "future_cal_rows_2873": int(manifest["future_cal_physical_rows"]) == 2873,
        "real_cal_not_authorized": manifest["real_distance_prior_cal_open_authorized"] is False,
        "joint_gate_not_authorized": manifest["joint_cal_gate_authorized"] is False,
        "test_rows_zero": int(manifest["test_rows_read"]) == 0,
        "test_sealed": manifest["test_open_authorized"] is False,
        "g2_not_evaluated": manifest["formal_g2"] == "NOT_EVALUATED",
    }
    checks = {k: bool(v) for k, v in checks.items()}
    failed = [k for k, v in checks.items() if not v]
    payload = {
        "phase": "F3.4f-2a",
        "component": "DG_DISTANCE_PRIOR",
        "status": "PASS" if not failed else "FAIL",
        "runbundle_gate": "PASS" if not failed else "FAIL",
        "mode": "SYNTHETIC_PREOPEN",
        "candidate_artifacts": 5,
        "candidate_selection": "NONE",
        "generated_draw_rows": 160,
        "synthetic_primary_rows": 5,
        "synthetic_summary_rows": 20,
        "cal_rows_read": 0,
        "test_rows_read": 0,
        "formal_g2": "NOT_EVALUATED",
        "checks": checks,
        "failed": failed,
    }
    print(json.dumps(payload, indent=2, sort_keys=True))
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
