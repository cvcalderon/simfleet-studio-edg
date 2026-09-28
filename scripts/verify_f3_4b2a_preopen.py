from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

import pandas as pd
import yaml

from simfleet_edg.evaluation.participation_cal_dryrun import (
    validate_frozen_participation_artifacts,
)

ROOT = Path.cwd()
REQUIRED_PARENT = "1c31cd3528b69bf24fb4434f7bde60188a8f8735"
OVERLAY_LIST = ROOT / "docs/F3_4B2A_OVERLAY_FILELIST_v1.txt"
CHECKSUMS = ROOT / "docs/F3_4B2A_OVERLAY_CHECKSUMS_v1.sha256"


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], text=True).strip()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def checksum_manifest_ok() -> bool:
    for line in CHECKSUMS.read_text().splitlines():
        if not line.strip():
            continue
        digest, relative = line.split(maxsplit=1)
        if sha256(ROOT / relative.strip()) != digest:
            return False
    return True


def witness_exact(config: dict, key: str) -> bool:
    witness = config["frozen_witnesses"][key]
    return sha256(ROOT / witness["path"]) == witness["sha256"]


def main() -> None:
    expected = {
        line.strip()
        for line in OVERLAY_LIST.read_text().splitlines()
        if line.strip()
    }
    actual = {
        line[3:]
        for line in git("status", "--porcelain").splitlines()
        if len(line) >= 4
    }
    config_path = ROOT / "configs/f3/f3_4b2a_participation_real_cal_preopen_v1.yaml"
    config = yaml.safe_load(config_path.read_text())
    registry = pd.read_csv(
        ROOT / "docs/F3_3_CANDIDATE_ARTIFACT_REGISTRY_v1.csv",
        dtype=str,
    )
    participation = registry.loc[
        registry["component"] == "DG_PARTICIPATION"
    ]
    artifact_validation = validate_frozen_participation_artifacts(ROOT)
    cal_root = ROOT / config["cal_input"]["root"]
    checks = {
        "head_exact_parent": git("rev-parse", "HEAD") == REQUIRED_PARENT,
        "branch_main": git("branch", "--show-current") == "main",
        "ahead_zero": git("rev-list", "--count", "origin/main..HEAD") == "0",
        "behind_zero": git("rev-list", "--count", "HEAD..origin/main") == "0",
        "no_staged_changes": git("diff", "--cached", "--name-only") == "",
        "overlay_scope_exact": actual == expected,
        "overlay_checksums_exact": checksum_manifest_ok(),
        "f3_4a_witness_exact": witness_exact(config, "f3_4a_contract"),
        "f3_4b1_witness_exact": witness_exact(config, "f3_4b1_dryrun"),
        "candidate_registry_exact": witness_exact(config, "candidate_registry"),
        "candidate_artifacts_exact_8": len(participation) == 8,
        "candidate_train_state_exact": set(participation["train_state"])
        == {"FITTED_TRAIN_ONLY_NOT_SELECTED"},
        "frozen_artifact_smoke_pass": len(artifact_validation) == 8
        and set(artifact_validation["synthetic_smoke"]) == {"PASS"},
        "cal_paths_exist_without_row_read": (
            (cal_root / "person_day_context.csv").is_file()
            and (cal_root / "participation.csv").is_file()
        ),
        "cal_rows_read_zero": config["entry_state"]["cal_rows_read"] == 0,
        "candidate_selection_none": (
            config["entry_state"]["candidate_selection"] == "NONE"
        ),
        "real_cal_not_authorized_in_preopen": (
            config["execution_authorization"][
                "real_cal_open_authorized_in_f3_4b2a"
            ]
            is False
        ),
        "external_commit_bound_authorization_required": (
            config["execution_authorization"][
                "must_bind_exact_implementation_commit"
            ]
            is True
        ),
        "test_still_sealed": (
            config["entry_state"]["test_partition"] == "SEALED"
            and config["entry_state"]["test_rows_read"] == 0
        ),
        "formal_g2_not_evaluated": config["formal_g2"] == "NOT_EVALUATED",
    }
    failed = [name for name, value in checks.items() if not value]
    result = {
        "phase": "F3.4b-2a",
        "status": "PASS" if not failed else "FAIL",
        "preopen_gate": "PASS" if not failed else "FAIL",
        "checks": checks,
        "failed": failed,
        "cal_rows_read": 0,
        "test_rows_read": 0,
        "candidate_selection": "NONE",
        "real_cal_open_authorized": False,
        "next_step_if_pass": (
            "COMMIT_IMPLEMENTATION_THEN_ISSUE_"
            "F3.4b-2b_COMMIT_BOUND_AUTHORIZATION"
        ),
        "test_open_authorized": False,
        "formal_g2": "NOT_EVALUATED",
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
