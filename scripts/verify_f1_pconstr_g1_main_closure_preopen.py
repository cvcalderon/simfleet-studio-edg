from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import subprocess
import zipfile
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
PARENT = "1aafadd95120c7875aac26f6504a6feb2aa5717a"
RUN_SHA = "8f37fb95d964ebd7c60d2ddf3befff10297b9e163438ac75d2caad9417877ea3"
RUNNER_SHA = "38fae45001fbd7adc73217915d20d3d06dbd8487d1201a4addc057a3e5cb3ecc"
THRESHOLD = "0.0815667541845037"
BERLIN = "0.016653027760625543"
WTVD = "0.0166531932467901"
MAXV = "0.023564294609585007"

OVERLAY_PATHS = [
    "configs/f1/f1_pconstr_g1_main_closure_v1.yaml",
    "docs/F1_PCONSTR_G1_A1_R1_DECISION_SNAPSHOT_v1.json",
    "docs/F1_PCONSTR_G1_A1_R1_METRICS_SNAPSHOT_v1.csv",
    "docs/F1_PCONSTR_G1_A1_R1_RUN_MANIFEST_SNAPSHOT_v1.json",
    "docs/F1_PCONSTR_G1_A1_R1_SOURCE_EVIDENCE_SNAPSHOT_v1.json",
    "docs/F1_PCONSTR_G1_A1_R1_VALIDATION_SNAPSHOT_v1.csv",
    "docs/F1_PCONSTR_G1_CLOSURE_OVERLAY_CHECKSUMS_v1.sha256",
    "docs/F1_PCONSTR_G1_CLOSURE_OVERLAY_FILELIST_v1.txt",
    "docs/F1_PCONSTR_G1_CLOSURE_v1.md",
    "docs/F1_PCONSTR_G1_MAIN_AUDIT_v1.json",
    "scripts/verify_f1_pconstr_g1_main_closure_preopen.py",
    "tests/test_f1_pconstr_g1_main_closure.py",
]

EXPECTED_RUN_MEMBERS = {
    "1000A-1035_de.csv",
    "F1_PCONSTR_G1_HOLDOUT_1000A_1035_A1_R1_runner.py",
    "bezirk_metrics.csv",
    "checksums.sha256",
    "decision.json",
    "environment.json",
    "g1_metrics.csv",
    "official_leaf_counts.csv",
    "run_manifest.json",
    "source_evidence.json",
    "synthetic_leaf_counts.csv",
    "synthetic_leaf_counts_sparse.csv",
    "validation.csv",
}


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def main() -> int:
    checks: dict[str, bool] = {}

    checks["branch_main"] = git("branch", "--show-current") == "main"
    checks["head_exact_parent"] = git("rev-parse", "HEAD") == PARENT
    checks["origin_exact_parent"] = git("rev-parse", "origin/main") == PARENT
    checks["no_staged_changes"] = git("diff", "--cached", "--name-only") == ""

    status_lines = [
        line for line in subprocess.check_output(
            ["git", "status", "--porcelain"], cwd=ROOT, text=True
        ).splitlines() if line.strip()
    ]
    actual_paths = sorted(line[3:] for line in status_lines)
    checks["overlay_scope_exact"] = actual_paths == sorted(OVERLAY_PATHS)

    checksum_file = ROOT / "docs/F1_PCONSTR_G1_CLOSURE_OVERLAY_CHECKSUMS_v1.sha256"
    checksum_ok = True
    for line in checksum_file.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        expected, rel = line.split("  ", 1)
        p = ROOT / rel
        if not p.exists() or sha256_bytes(p.read_bytes()) != expected:
            checksum_ok = False
    checks["overlay_checksums_pass"] = checksum_ok

    cfg = yaml.safe_load(
        (ROOT / "configs/f1/f1_pconstr_g1_main_closure_v1.yaml").read_text(encoding="utf-8")
    )
    checks["config_parent_exact"] = cfg["required_parent_commit"] == PARENT
    checks["candidate_exact"] = cfg["selected_population"]["candidate_id"] == "P_CONSTR_RMIN_V2_HD_U"
    checks["scale_M"] = cfg["selected_population"]["scale_id"] == "M"
    checks["G1_pass"] = cfg["official_result"]["G1"] == "PASS"
    checks["status_after_commit_closed"] = cfg["status_after_commit"] == "G1_PASS_CLOSED"
    checks["G2_closed"] = cfg["controlled_state_after_commit"]["G2"] == "PASS_CLOSED_DO_NOT_REOPEN"
    checks["test_closed"] = cfg["controlled_state_after_commit"]["MiD_TEST"] == "CONSUMED_BY_G2_DO_NOT_REOPEN"
    checks["cal_closed"] = cfg["controlled_state_after_commit"]["CAL"] == "CLOSED_DO_NOT_REOPEN"
    checks["holdout_consumed"] = all([
        cfg["controlled_state_after_commit"]["holdout_1000A_1035_acquired"] is True,
        cfg["controlled_state_after_commit"]["holdout_1000A_1035_values_read"] is True,
        cfg["controlled_state_after_commit"]["holdout_1000A_1035_evaluated"] is True,
    ])

    run_zip = Path(
        os.environ.get(
            "F1_G1_RUN_ZIP",
            str(Path.home() / "Downloads/F1_PCONSTR_G1_HOLDOUT_1000A_1035_A1_R1_official_run_v1.zip"),
        )
    )
    checks["run_zip_exists"] = run_zip.exists()
    if run_zip.exists():
        checks["run_zip_hash_exact"] = sha256_bytes(run_zip.read_bytes()) == RUN_SHA
        with zipfile.ZipFile(run_zip) as zf:
            checks["run_zip_integrity"] = zf.testzip() is None
            checks["run_members_exact"] = set(zf.namelist()) == EXPECTED_RUN_MEMBERS

            raw_checksums = zf.read("checksums.sha256").decode("utf-8")
            internal_ok = True
            for line in raw_checksums.splitlines():
                if not line.strip():
                    continue
                expected, name = line.split("  ", 1)
                if name not in zf.namelist() or sha256_bytes(zf.read(name)) != expected:
                    internal_ok = False
            checks["run_internal_checksums"] = internal_ok

            runner_name = "F1_PCONSTR_G1_HOLDOUT_1000A_1035_A1_R1_runner.py"
            checks["runner_hash_exact"] = sha256_bytes(zf.read(runner_name)) == RUNNER_SHA

            run_metrics = list(csv.DictReader(io.StringIO(zf.read("g1_metrics.csv").decode("utf-8"))))
            snap_metrics = list(csv.DictReader((ROOT / "docs/F1_PCONSTR_G1_A1_R1_METRICS_SNAPSHOT_v1.csv").open(encoding="utf-8", newline="")))
            checks["metrics_snapshot_exact"] = run_metrics == snap_metrics

            run_decision = json.loads(zf.read("decision.json"))
            snap_decision = json.loads((ROOT / "docs/F1_PCONSTR_G1_A1_R1_DECISION_SNAPSHOT_v1.json").read_text(encoding="utf-8"))
            checks["decision_snapshot_exact"] = run_decision == snap_decision

            run_validation = list(csv.DictReader(io.StringIO(zf.read("validation.csv").decode("utf-8"))))
            snap_validation = list(csv.DictReader((ROOT / "docs/F1_PCONSTR_G1_A1_R1_VALIDATION_SNAPSHOT_v1.csv").open(encoding="utf-8", newline="")))
            checks["validation_snapshot_exact"] = run_validation == snap_validation
            checks["validation_all_pass"] = all(row["status"] == "PASS" for row in run_validation)

            run_source = json.loads(zf.read("source_evidence.json"))
            snap_source = json.loads((ROOT / "docs/F1_PCONSTR_G1_A1_R1_SOURCE_EVIDENCE_SNAPSHOT_v1.json").read_text(encoding="utf-8"))
            checks["source_evidence_snapshot_exact"] = run_source == snap_source

            run_manifest = json.loads(zf.read("run_manifest.json"))
            snap_manifest = json.loads((ROOT / "docs/F1_PCONSTR_G1_A1_R1_RUN_MANIFEST_SNAPSHOT_v1.json").read_text(encoding="utf-8"))
            checks["run_manifest_snapshot_exact"] = run_manifest == snap_manifest
    else:
        for key in [
            "run_zip_hash_exact", "run_zip_integrity", "run_members_exact",
            "run_internal_checksums", "runner_hash_exact", "metrics_snapshot_exact",
            "decision_snapshot_exact", "validation_snapshot_exact",
            "validation_all_pass", "source_evidence_snapshot_exact",
            "run_manifest_snapshot_exact",
        ]:
            checks[key] = False

    snap_metrics_by_id = {
        row["metric_id"]: row for row in csv.DictReader(
            (ROOT / "docs/F1_PCONSTR_G1_A1_R1_METRICS_SNAPSHOT_v1.csv").open(encoding="utf-8", newline="")
        )
    }
    checks["berlin_value_exact"] = snap_metrics_by_id["G1-HOLD-SEN-BERLIN-TVD"]["value"] == BERLIN
    checks["wtvd_value_exact"] = snap_metrics_by_id["G1-HOLD-SEN-BEZ-WTVD"]["value"] == WTVD
    checks["max_value_exact"] = snap_metrics_by_id["G1-HOLD-SEN-BEZ-MAX"]["value"] == MAXV
    checks["threshold_exact"] = (
        snap_metrics_by_id["G1-HOLD-SEN-BERLIN-TVD"]["threshold"] == THRESHOLD
        and snap_metrics_by_id["G1-HOLD-SEN-BEZ-WTVD"]["threshold"] == THRESHOLD
    )
    checks["both_decision_pass"] = (
        snap_metrics_by_id["G1-HOLD-SEN-BERLIN-TVD"]["decision"] == "PASS"
        and snap_metrics_by_id["G1-HOLD-SEN-BEZ-WTVD"]["decision"] == "PASS"
    )
    checks["max_report_only"] = snap_metrics_by_id["G1-HOLD-SEN-BEZ-MAX"]["role"] == "REPORT_ONLY"

    failed = sorted(k for k, v in checks.items() if not v)
    result = {
        "phase": "F1-P_CONSTR-G1 MAIN CLOSURE PREOPEN",
        "parent": PARENT,
        "selected_candidate": "P_CONSTR_RMIN_V2_HD_U",
        "runbundle_zip_sha256": RUN_SHA,
        "checks": checks,
        "failed": failed,
        "status": "PASS" if not failed else "FAIL",
        "controlled_state_after_commit": cfg["controlled_state_after_commit"],
        "next_step_if_pass": "COMMIT_AND_PUSH_G1_MAIN_CLOSURE",
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
