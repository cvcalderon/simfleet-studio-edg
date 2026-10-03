from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
PARENT = "beeb79a79e81aaaff3041542c3a9f3c08937e1dc"
EXECUTION_COMMIT = "beeb79a79e81aaaff3041542c3a9f3c08937e1dc"
CFG = ROOT / "configs/f3/f3_4g2d_joint_cal_a1_closure_v1.yaml"
SNAPSHOT = ROOT / "docs/F3_4G2D_JOINT_METRICS_A1_SNAPSHOT_v1.csv"
FILELIST = ROOT / "docs/F3_4G2D_OVERLAY_FILELIST_v1.txt"
CHECKSUMS = ROOT / "docs/F3_4G2D_OVERLAY_CHECKSUMS_v1.sha256"


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).rstrip("\n")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def verify_manifest(base: Path, manifest_path: Path) -> bool:
    for line in manifest_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        expected, rel = line.split(maxsplit=1)
        path = base / rel.strip()
        if not path.is_file() or sha256_file(path) != expected:
            return False
    return True


def verify_runbundle_checksums(run: Path) -> bool:
    manifest = run / "checksums.sha256"
    if not manifest.is_file():
        return False
    return verify_manifest(run, manifest)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", required=True)
    args = parser.parse_args()

    run = Path(args.run_dir).expanduser().resolve()
    manifest = json.loads((run / "run_manifest.json").read_text(encoding="utf-8"))
    gate = json.loads((run / "joint_gate.json").read_text(encoding="utf-8"))
    access = json.loads((run / "cal_access_manifest.json").read_text(encoding="utf-8"))
    metrics = pd.read_csv(run / "joint_metrics.csv")
    snapshot = pd.read_csv(SNAPSHOT)
    validation = pd.read_csv(run / "validation.csv")
    issues = pd.read_csv(run / "issues.csv")

    expected_scope = set(FILELIST.read_text(encoding="utf-8").splitlines())
    actual_scope = {
        line[3:]
        for line in git("status", "--short").splitlines()
        if line
    }

    decision = metrics.loc[metrics["decision_role"].ne("REPORT_ONLY")]
    report = metrics.loc[metrics["decision_role"].eq("REPORT_ONLY")]
    worsened = decision.loc[
        decision["selected_minus_reference_worsening"].astype(float) > 0
    ]

    checks = {
        "head_exact_parent": git("rev-parse", "HEAD") == PARENT,
        "branch_main": git("branch", "--show-current") == "main",
        "ahead_zero": git("rev-list", "--count", "origin/main..HEAD") == "0",
        "behind_zero": git("rev-list", "--count", "HEAD..origin/main") == "0",
        "no_staged_changes": git("diff", "--cached", "--name-only") == "",
        "overlay_scope_exact": actual_scope == expected_scope,
        "overlay_checksums_pass": verify_manifest(ROOT, CHECKSUMS),
        "runbundle_checksums_pass": verify_runbundle_checksums(run),
        "execution_commit_exact": manifest["implementation_commit"] == EXECUTION_COMMIT,
        "execution_status_pass": manifest["status"] == "PASS",
        "cal_rows_6341": int(manifest["cal_rows_read_total_physical"]) == 6341,
        "eight_cal_files": len(access["cal_files_opened"]) == 8,
        "artifact_slots_10": int(manifest["pipeline_artifact_slots"]) == 10,
        "replicates_32": int(manifest["stochastic_replicates"]) == 32,
        "candidate_selection_none": manifest["candidate_selection"] == "NONE",
        "joint_gate_pass": gate["pass_gate"] is True,
        "joint_gate_reasons_empty": gate["reasons"] == [],
        "structural_zero": int(gate["structural_invariant_violations"]) == 0,
        "temporal_zero": int(gate["temporal_invariant_violations"]) == 0,
        "nofuture_zero": int(gate["nofuture_violations"]) == 0,
        "component_not_dominated": gate["selected_component_dominated"] is False,
        "no_material_degradation": (
            gate["selected_pipeline_material_degradation"] is False
        ),
        "metrics_17": len(metrics) == 17,
        "decision_metrics_14": len(decision) == 14,
        "decision_metrics_all_pass": decision["gate_pass"].astype(bool).all(),
        "report_only_3": len(report) == 3,
        "positive_decision_worsening_2": len(worsened) == 2,
        "metric_snapshot_exact": metrics.equals(snapshot),
        "validation_all_pass": validation["status"].eq("PASS").all(),
        "issues_empty": len(issues) == 0,
        "test_eligible": gate["test_eligible_by_joint_gate"] is True,
        "test_still_closed": manifest["test_open_authorized"] is False,
        "test_rows_zero": int(manifest["test_rows_read"]) == 0,
        "g2_not_evaluated": manifest["formal_g2"] == "NOT_EVALUATED",
    }

    failed = [name for name, passed in checks.items() if not bool(passed)]
    payload = {
        "phase": "F3.4g-2d",
        "component": "DGEN_JOINT_PIPELINE",
        "status": "PASS" if not failed else "FAIL",
        "closure_gate": "PASS" if not failed else "FAIL",
        "joint_cal_a1_status": "CLOSED_PASS" if not failed else "NOT_CLOSED",
        "decision_metrics_pass": int(decision["gate_pass"].astype(bool).sum()),
        "decision_metrics_total": len(decision),
        "report_only_metrics": len(report),
        "positive_worsening_decision_metrics": worsened["metric_id"].astype(str).tolist(),
        "test_eligible_by_joint_gate": bool(gate["test_eligible_by_joint_gate"]),
        "test_open_authorized": False,
        "test_rows_read": int(manifest["test_rows_read"]),
        "formal_g2": manifest["formal_g2"],
        "checks": {name: bool(value) for name, value in checks.items()},
        "failed": failed,
        "next_step_if_pass": "COMMIT_CLOSURE_THEN_FREEZE_HELD_OUT_TEST_PROTOCOL",
    }
    print(json.dumps(payload, indent=2, sort_keys=True))
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
