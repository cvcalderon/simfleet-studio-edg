from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import tempfile
from pathlib import Path

import pandas as pd
import yaml

from simfleet_edg.evaluation.trip_count_cal_preopen import (
    run_synthetic_trip_count_preopen,
)

ROOT = Path.cwd()
REQUIRED_PARENT = "5b29b668a2e4367c11661c70dbd15beb27070377"
EXPECTED_CONTRACT_SHA = "e5be950802b3bb7ae72a223cbae529e0136b1f73f7002581fc953a1b92a279e4"
EXPECTED_FREEZE_SHA = "025eb31f3c4ef04d838bd3c92bb05349b43820a75bc81112adc3631b8070ea75"
EXPECTED_REGISTRY_SHA = "52328037d9a57866b188166373f798da4fb97460fc794748f8f0ef3968e86ad8"
OVERLAY_LIST = ROOT / "docs/F3_4C2A_OVERLAY_FILELIST_v1.txt"
CHECKSUMS = ROOT / "docs/F3_4C2A_OVERLAY_CHECKSUMS_v1.sha256"


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], text=True).strip()


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def checksum_manifest_ok() -> bool:
    for line in CHECKSUMS.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        digest, rel = line.split(maxsplit=1)
        if sha256(ROOT / rel.strip()) != digest:
            return False
    return True


def main() -> None:
    expected = {
        line.strip()
        for line in OVERLAY_LIST.read_text(encoding="utf-8").splitlines()
        if line.strip()
    }
    status = git("status", "--porcelain").splitlines()
    actual = {line[3:] for line in status if len(line) >= 4}
    cfg = yaml.safe_load(
        (
            ROOT / "configs/f3/f3_4c2a_trip_count_real_cal_preopen_v1.yaml"
        ).read_text(encoding="utf-8")
    )
    registry = pd.read_csv(
        ROOT / "docs/F3_3_CANDIDATE_ARTIFACT_REGISTRY_v1.csv",
        dtype=str,
    )
    count = registry.loc[registry["component"] == "DG_TRIP_COUNT"]
    pa1 = registry.loc[
        registry["artifact_id"] == "DG_PARTICIPATION::PART_A::PA1"
    ]

    temp = Path(tempfile.mkdtemp(prefix="f3_4c2a_verify_"))
    try:
        manifest = run_synthetic_trip_count_preopen(
            ROOT,
            temp,
            validate_artifacts=True,
        )
        access = json.loads((temp / "cal_access_manifest.json").read_text())
        selected = json.loads(
            (temp / "selected_component_artifact.json").read_text()
        )
        validation = pd.read_csv(temp / "validation.csv")
        checks = {
            "head_exact_parent": git("rev-parse", "HEAD") == REQUIRED_PARENT,
            "branch_main": git("branch", "--show-current") == "main",
            "ahead_zero": git("rev-list", "--count", "origin/main..HEAD") == "0",
            "behind_zero": git("rev-list", "--count", "HEAD..origin/main") == "0",
            "no_staged_changes": git("diff", "--cached", "--name-only") == "",
            "overlay_scope_exact": actual == expected,
            "overlay_checksums_exact": checksum_manifest_ok(),
            "f3_4c1_contract_exact": sha256(
                ROOT / "configs/f3/f3_4c1_trip_count_cal_contract_v1.yaml"
            ) == EXPECTED_CONTRACT_SHA,
            "upstream_freeze_exact": sha256(
                ROOT / "configs/f3/f3_4b2c_participation_main_freeze_v1.yaml"
            ) == EXPECTED_FREEZE_SHA,
            "candidate_registry_exact": sha256(
                ROOT / "docs/F3_3_CANDIDATE_ARTIFACT_REGISTRY_v1.csv"
            ) == EXPECTED_REGISTRY_SHA,
            "candidate_artifacts_exact_5": len(count) == 5,
            "candidate_train_state_exact": set(count["train_state"])
            == {"FITTED_TRAIN_ONLY_NOT_SELECTED"},
            "upstream_pa1_exact": len(pa1) == 1,
            "synthetic_preopen_pass": manifest["status"] == "PASS",
            "new_trip_count_cal_rows_zero": (
                manifest["new_trip_count_cal_rows_read"] == 0
                and access["new_trip_count_cal_rows_read"] == 0
            ),
            "test_rows_zero": (
                manifest["test_rows_read"] == 0
                and access["test_rows_read"] == 0
            ),
            "no_cal_files_opened": access["cal_files_opened"] == [],
            "no_test_files_opened": access["test_files_opened"] == [],
            "candidate_selection_none": (
                manifest["candidate_selection"] == "NONE"
                and selected["candidate_selection"] == "NONE"
            ),
            "real_cal_not_authorized": (
                cfg["preopen"]["real_trip_count_cal_open_authorized"] is False
            ),
            "test_still_sealed": cfg["preopen"]["test_open_authorized"] is False,
            "formal_g2_not_evaluated": cfg["preopen"]["formal_g2"]
            == "NOT_EVALUATED",
            "validation_all_pass": set(validation["status"]) == {"PASS"},
        }
    finally:
        shutil.rmtree(temp, ignore_errors=True)

    failed = [name for name, value in checks.items() if not value]
    result = {
        "phase": "F3.4c-2a",
        "status": "PASS" if not failed else "FAIL",
        "preopen_gate": "PASS" if not failed else "FAIL",
        "component": "DG_TRIP_COUNT",
        "candidate_artifacts": 5,
        "new_trip_count_cal_rows_read": 0,
        "candidate_selection": "NONE",
        "real_trip_count_cal_open_authorized": False,
        "test_rows_read": 0,
        "test_open_authorized": False,
        "formal_g2": "NOT_EVALUATED",
        "next_step_if_pass": (
            "COMMIT_IMPLEMENTATION_THEN_ISSUE_F3.4c-2b_COMMIT_BOUND_AUTHORIZATION"
        ),
        "checks": checks,
        "failed": failed,
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
