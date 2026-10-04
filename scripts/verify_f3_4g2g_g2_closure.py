from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path

import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[1]
PARENT = "911abb2ee194d9c3529880f26ba4773eb82c821d"
CFG = ROOT / "configs/f3/f3_4g2g_heldout_test_a1_closure_v1.yaml"
METRICS_SNAPSHOT = ROOT / "docs/F3_4G2G_TEST_METRICS_A1_SNAPSHOT_v1.csv"
EVIDENCE = ROOT / "docs/F3_4G2G_TEST_A1_EVIDENCE_SUMMARY_v1.json"
FILELIST = ROOT / "docs/F3_4G2G_OVERLAY_FILELIST_v1.txt"
CHECKSUMS = ROOT / "docs/F3_4G2G_OVERLAY_CHECKSUMS_v1.sha256"


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).rstrip("\n")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def verify_overlay_checksums() -> bool:
    for line in CHECKSUMS.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        expected, rel = line.split(maxsplit=1)
        path = ROOT / rel.strip()
        if not path.is_file() or sha256_file(path) != expected:
            return False
    return True


def verify_run_checksums(run: Path) -> bool:
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
    cfg = yaml.safe_load(CFG.read_text(encoding="utf-8"))
    manifest = json.loads((run / "run_manifest.json").read_text(encoding="utf-8"))
    g2 = json.loads((run / "g2_decision.json").read_text(encoding="utf-8"))
    consumption = json.loads(
        (run / "holdout_consumption.json").read_text(encoding="utf-8")
    )
    materialization = json.loads(
        (run / "test_materialization_manifest.json").read_text(encoding="utf-8")
    )
    source_validation = pd.read_csv(run / "source_hash_validation.csv")
    artifacts = pd.read_csv(run / "pipeline_artifact_validation.csv")
    metrics = pd.read_csv(run / "test_metrics.csv")
    snapshot = pd.read_csv(METRICS_SNAPSHOT)
    validation = pd.read_csv(run / "validation.csv")
    issues = pd.read_csv(run / "issues.csv")
    evidence = json.loads(EVIDENCE.read_text(encoding="utf-8"))

    expected_scope = set(FILELIST.read_text(encoding="utf-8").splitlines())
    actual_scope = {
        line[3:]
        for line in git("status", "--short").splitlines()
        if line
    }

    decision = metrics.loc[metrics["decision_role"].ne("REPORT_ONLY")]
    report = metrics.loc[metrics["decision_role"].eq("REPORT_ONLY")]
    decision_with_headroom = decision.copy()
    decision_with_headroom["headroom"] = (
        decision_with_headroom["max_worsening"].astype(float)
        - decision_with_headroom[
            "selected_minus_reference_worsening"
        ].astype(float)
    )
    closest = decision_with_headroom.sort_values("headroom").iloc[0]

    materialized = run / "materialized_test"
    materialized_hashes_ok = True
    for dataset, expected in materialization["table_sha256"].items():
        path = materialized / f"{dataset}.csv"
        if not path.is_file() or sha256_file(path) != expected:
            materialized_hashes_ok = False

    checks = {
        "head_exact_parent": git("rev-parse", "HEAD") == PARENT,
        "branch_main": git("branch", "--show-current") == "main",
        "ahead_zero": git("rev-list", "--count", "origin/main..HEAD") == "0",
        "behind_zero": git("rev-list", "--count", "HEAD..origin/main") == "0",
        "no_staged_changes": git("diff", "--cached", "--name-only") == "",
        "overlay_scope_exact": actual_scope == expected_scope,
        "overlay_checksums_pass": verify_overlay_checksums(),
        "runbundle_checksums_pass": verify_run_checksums(run),
        "execution_commit_exact": manifest["implementation_commit"] == PARENT,
        "execution_status_pass": manifest["status"] == "PASS",
        "formal_g2_pass": manifest["formal_g2"] == "PASS",
        "g2_matches": g2["formal_g2"] == "PASS",
        "holdout_consumed": consumption["holdout_consumed"] is True,
        "same_holdout_rerun_forbidden": (
            manifest["same_holdout_rerun_authorized"] is False
        ),
        "post_test_tuning_forbidden": (
            manifest["post_test_tuning_authorized"] is False
        ),
        "strict_test_households_260": manifest["strict_test_households"] == 260,
        "source_hashes_13_pass": (
            len(source_validation) == 13
            and source_validation["status"].eq("PASS").all()
        ),
        "materialized_table_hashes_8_pass": (
            len(materialization["table_sha256"]) == 8
            and materialized_hashes_ok
        ),
        "artifact_slots_10": len(artifacts) == 10,
        "artifact_validation_all_pass": artifacts["status"].eq("PASS").all(),
        "metrics_17": len(metrics) == 17,
        "decision_metrics_14": len(decision) == 14,
        "decision_metrics_all_pass": decision["gate_pass"].astype(bool).all(),
        "report_only_3": len(report) == 3,
        "hard_invariants_zero": (
            int(g2["structural_invariant_violations"]) == 0
            and int(g2["temporal_invariant_violations"]) == 0
            and int(g2["nofuture_violations"]) == 0
        ),
        "closest_metric_positive_headroom": float(closest["headroom"]) > 0.0,
        "metric_snapshot_exact": metrics.equals(snapshot),
        "validation_all_pass": validation["status"].eq("PASS").all(),
        "issues_empty": len(issues) == 0,
        "evidence_summary_g2_pass": evidence["formal_g2"] == "PASS",
        "g1_still_open": cfg["project_gate_note"]["formal_g1"] == "OPEN",
    }

    failed = [name for name, passed in checks.items() if not bool(passed)]
    payload = {
        "phase": "F3.4g-2g",
        "component": "DGEN_JOINT_PIPELINE",
        "status": "PASS" if not failed else "FAIL",
        "closure_gate": "PASS" if not failed else "FAIL",
        "heldout_test_a1_status": (
            "CLOSED_G2_PASS" if not failed else "NOT_CLOSED"
        ),
        "formal_g1": "OPEN",
        "formal_g2": manifest["formal_g2"],
        "decision_metrics_pass": int(
            decision["gate_pass"].astype(bool).sum()
        ),
        "decision_metrics_total": len(decision),
        "report_only_metrics": len(report),
        "closest_metric_to_threshold": {
            "metric_id": str(closest["metric_id"]),
            "worsening": float(
                closest["selected_minus_reference_worsening"]
            ),
            "max_worsening": float(closest["max_worsening"]),
            "headroom": float(closest["headroom"]),
        },
        "strict_test_households": manifest["strict_test_households"],
        "generated_day_rows": manifest["generated_day_rows"],
        "generated_trip_rows": manifest["generated_trip_rows"],
        "holdout_consumed": True,
        "same_holdout_rerun_authorized": False,
        "post_test_tuning_authorized": False,
        "checks": {name: bool(value) for name, value in checks.items()},
        "failed": failed,
        "next_step_if_pass": "COMMIT_G2_CLOSURE",
    }
    print(json.dumps(payload, indent=2, sort_keys=True))
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
