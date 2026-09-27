from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

import pandas as pd
import yaml

from simfleet_edg.evaluation.cal_access_guard import PartitionAccess
from simfleet_edg.evaluation.cal_adapter_common import ArtifactRecord
from simfleet_edg.evaluation.cal_harness import REPLICATES, packed_draw_index

ROOT = Path.cwd()
PARENT = "9bb4e40ecb00ba29a5c1765b9492cd18ffba0569"
FILELIST = ROOT / "docs/F3_3C_EXECUTION_HARNESS_OVERLAY_FILELIST_v1.txt"
CHECKSUMS = ROOT / "docs/F3_3C_EXECUTION_HARNESS_OVERLAY_CHECKSUMS_v1.sha256"
CONFIG = ROOT / "configs/f3/f3_3c_pre_cal_execution_harness_v1.yaml"
REGISTRY = ROOT / "docs/F3_3_CANDIDATE_ARTIFACT_REGISTRY_v1.csv"


def run(*args: str) -> str:
    return subprocess.check_output(args, cwd=ROOT, text=True).strip()


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    cfg = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    expected_paths = [x for x in FILELIST.read_text(encoding="utf-8").splitlines() if x]
    expected = set(expected_paths)

    checks: dict[str, bool] = {}
    checks["head_exact_parent"] = run("git", "rev-parse", "HEAD") == PARENT
    checks["branch_main"] = run("git", "branch", "--show-current") == "main"
    ahead, behind = run("git", "rev-list", "--left-right", "--count", "HEAD...origin/main").split()
    checks["ahead_zero"] = ahead == "0"
    checks["behind_zero"] = behind == "0"
    checks["no_staged_changes"] = run("git", "diff", "--cached", "--name-only") == ""

    status_lines = run("git", "status", "--porcelain").splitlines()
    changed = {line[3:] for line in status_lines if line}
    checks["overlay_scope_exact"] = changed == expected

    checksum_ok = True
    for line in CHECKSUMS.read_text(encoding="utf-8").splitlines():
        digest, rel = line.split("  ", 1)
        checksum_ok &= sha256(ROOT / rel) == digest
    checks["overlay_checksums_exact"] = bool(checksum_ok)

    protocol = cfg["protocol"]
    boundaries = cfg["boundaries"]
    checks["32_replicates"] = protocol["stochastic_replicates"] == 32 == REPLICATES
    checks["1000_bootstraps"] = protocol["household_bootstrap_replicates"] == 1000
    checks["confidence_95"] = float(protocol["confidence_level"]) == 0.95
    checks["paired_crn"] = protocol["paired_crn"] is True
    checks["draw_pack_exact"] = packed_draw_index(31, 7) == (31 << 32) | 7
    checks["person_id_contract"] = protocol["evaluation_person_id"] == "CAL_PIPE_HH_PERSON_V1"
    checks["metric_rep_aggregation"] = (
        protocol["metric_replicate_aggregation"] == "ARITHMETIC_MEAN_OF_32_V1"
    )
    checks["bootstrap_interval"] = protocol["bootstrap_interval"] == "PERCENTILE_95_V1"
    checks["cal_unopened"] = boundaries["cal_open_authorized"] is False
    checks["test_sealed"] = boundaries["test_open_authorized"] is False
    checks["selection_none"] = boundaries["candidate_selection"] == "NONE"
    checks["cal_rows_read_zero"] = boundaries["cal_rows_read"] == 0
    checks["test_rows_read_zero"] = boundaries["test_rows_read"] == 0
    checks["ids_not_features"] = boundaries["ids_are_behavioral_features"] is False

    guard = PartitionAccess()
    try:
        guard.assert_pre_cal()
        guard.require_cal()
    except PermissionError:
        checks["cal_open_blocked"] = True
    else:
        checks["cal_open_blocked"] = False
    try:
        guard.require_test()
    except PermissionError:
        checks["test_open_blocked"] = True
    else:
        checks["test_open_blocked"] = False

    registry = pd.read_csv(REGISTRY, dtype=str)
    checks["registry_rows_31"] = len(registry) == 31
    artifact_checks = 0
    for _, row in registry.iterrows():
        record = ArtifactRecord.from_series(row)
        ok = True
        try:
            record.validate(ROOT)
        except Exception:
            ok = False
        checks[f"artifact:{record.artifact_id}"] = ok
        artifact_checks += 1

    failed = [key for key, value in checks.items() if not bool(value)]
    print(json.dumps({
        "status": "PASS" if not failed else "FAIL",
        "artifact_checks": artifact_checks,
        "cal_rows_read": 0,
        "test_rows_read": 0,
        "checks": {k: bool(v) for k, v in checks.items()},
        "failed": failed,
    }, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
