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
    access = json.loads(
        (run / "cal_access_manifest.json").read_text(encoding="utf-8")
    )
    gate = json.loads((run / "joint_gate.json").read_text(encoding="utf-8"))
    inputs = pd.read_csv(run / "input_validation.csv")
    artifacts = pd.read_csv(run / "pipeline_artifact_validation.csv")
    metrics = pd.read_csv(run / "joint_metrics.csv")
    validation = pd.read_csv(run / "validation.csv")
    issues = pd.read_csv(run / "issues.csv")

    required_metric_ids = {
        "M2-PART-01",
        "M2-COND-01",
        "M2-COUNT-01",
        "M2-COUNT-02",
        "M2-CHAIN-01",
        "M2-COND-02",
        "M2-PURP-01",
        "M2-TRANS-01",
        "M2-RET-01",
        "M2-TIME-01",
        "TIME-CIRCULAR-W1",
        "M2-DIST-01",
        "DIST-MEAN",
        "DIST-P50",
        "DIST-P90",
        "DIST-P95",
        "M2-DIST-02",
    }

    checks = {
        "run_status_pass": manifest["status"] == "PASS",
        "phase_exact": manifest["phase"] == "F3.4g-2c",
        "mode_real_cal": manifest["mode"] == "CONTROLLED_REAL_CAL",
        "checksums_ok": verify_checksums(run),
        "cal_rows_6341": int(manifest["cal_rows_read_total_physical"]) == 6341,
        "access_rows_6341": int(access["cal_rows_read_total_physical"]) == 6341,
        "eight_cal_inputs": len(inputs) == 8,
        "input_validation_all_pass": inputs["status"].eq("PASS").all(),
        "ten_artifact_slots": len(artifacts) == 10,
        "artifact_validation_all_pass": artifacts["status"].eq("PASS").all(),
        "metric_matrix_complete": set(metrics["metric_id"]) == required_metric_ids,
        "validation_all_pass": validation["status"].eq("PASS").all(),
        "issues_empty": len(issues) == 0,
        "candidate_selection_none": manifest["candidate_selection"] == "NONE",
        "joint_gate_evaluated": manifest["joint_gate_evaluated"] is True,
        "gate_pass_matches": bool(manifest["joint_gate_pass"]) == bool(
            gate["pass_gate"]
        ),
        "test_eligibility_matches": bool(manifest["test_eligible_by_joint_gate"])
        == bool(gate["test_eligible_by_joint_gate"]),
        "test_still_closed": manifest["test_open_authorized"] is False,
        "test_rows_zero": int(manifest["test_rows_read"]) == 0,
        "g2_not_evaluated": manifest["formal_g2"] == "NOT_EVALUATED",
    }

    failed = [name for name, value in checks.items() if not bool(value)]
    payload = {
        "phase": "F3.4g-2c",
        "component": "DGEN_JOINT_PIPELINE",
        "status": "PASS" if not failed else "FAIL",
        "runbundle_gate": "PASS" if not failed else "FAIL",
        "execution_status": manifest["status"],
        "joint_gate_pass": bool(manifest["joint_gate_pass"]),
        "joint_gate_reasons": manifest["joint_gate_reasons"],
        "cal_rows_read": int(manifest["cal_rows_read_total_physical"]),
        "pipeline_artifact_slots": len(artifacts),
        "metric_rows": len(metrics),
        "candidate_selection": manifest["candidate_selection"],
        "test_eligible_by_joint_gate": bool(
            manifest["test_eligible_by_joint_gate"]
        ),
        "test_open_authorized": False,
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
