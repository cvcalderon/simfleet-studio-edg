from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[1]
PARENT = "18a8b7921b7af14d7cd6f31e37a6624f4ac551b1"
CFG = ROOT / "configs/f3/f3_4g2f_heldout_test_runner_preopen_v1.yaml"
FILELIST = ROOT / "docs/F3_4G2F_OVERLAY_FILELIST_v1.txt"
CHECKSUMS = ROOT / "docs/F3_4G2F_OVERLAY_CHECKSUMS_v1.sha256"
NEGATIVE = ROOT / "configs/f3/f3_4g2e_test_authorization_TEMPLATE_v1.json"


def git(*args: str) -> str:
    return subprocess.check_output(
        ["git", *args],
        cwd=ROOT,
        text=True,
    ).rstrip("\n")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def verify_overlay_checksums() -> bool:
    for line in CHECKSUMS.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        expected, rel = line.split(maxsplit=1)
        path = ROOT / rel.strip()
        if not path.is_file() or sha256_file(path) != expected:
            return False
    return True


def main() -> None:
    cfg = yaml.safe_load(CFG.read_text(encoding="utf-8"))
    expected_scope = set(FILELIST.read_text(encoding="utf-8").splitlines())
    actual_scope = {
        line[3:]
        for line in git("status", "--short").splitlines()
        if line
    }

    split_path = ROOT / cfg["split_identity"]["path"]
    split = pd.read_csv(split_path)
    strict_test = split.loc[
        split["split"].eq("TEST")
        & split["joint_rmin_donor_eligible"]
        .astype(str)
        .str.lower()
        .isin({"true", "1", "yes"})
    ]

    original_contract = yaml.safe_load(
        (
            ROOT
            / cfg["materializer_reuse"]["original_contract"]
        ).read_text(encoding="utf-8")
    )
    runtime_vocab = json.loads(
        (
            ROOT
            / cfg["materializer_reuse"]["frozen_train_vocabulary"][
                "runtime_path"
            ]
        ).read_text(encoding="utf-8")
    )
    snapshot_vocab = json.loads(
        (
            ROOT
            / cfg["materializer_reuse"]["frozen_train_vocabulary"][
                "semantic_snapshot"
            ]
        ).read_text(encoding="utf-8")
    )
    negative = json.loads(NEGATIVE.read_text(encoding="utf-8"))
    test_dir = (
        ROOT
        / "artifacts/model_data/F3_2a_training_data_v1/TEST"
    )

    checks = {
        "head_exact_parent": git("rev-parse", "HEAD") == PARENT,
        "branch_main": git("branch", "--show-current") == "main",
        "ahead_zero": git("rev-list", "--count", "origin/main..HEAD") == "0",
        "behind_zero": git("rev-list", "--count", "HEAD..origin/main") == "0",
        "no_staged_changes": git("diff", "--cached", "--name-only") == "",
        "overlay_scope_exact": actual_scope == expected_scope,
        "overlay_checksums_pass": verify_overlay_checksums(),
        "split_hash_exact": (
            sha256_file(split_path) == cfg["split_identity"]["sha256"]
        ),
        "strict_test_households_260": len(strict_test) == 260,
        "strict_test_household_ids_unique": (
            strict_test["source_household_id"].nunique(dropna=False) == 260
        ),
        "original_contract_test_forbidden": (
            "TEST" in original_contract["partitions"]["forbidden"]
        ),
        "original_contract_allowed_train_cal_only": (
            original_contract["partitions"]["allowed"]
            == ["TRAIN", "CALIBRATION"]
        ),
        "runtime_train_vocabulary_matches_snapshot": (
            runtime_vocab == snapshot_vocab
        ),
        "test_dir_absent_preopen": not test_dir.exists(),
        "negative_template_test_closed": (
            negative["heldout_test_open_authorized"] is False
        ),
        "negative_template_g2_closed": (
            negative["formal_g2_evaluation_authorized"] is False
        ),
        "runner_implemented": (
            ROOT
            / "src/simfleet_edg/repro/f3_4g2f_heldout_test_runner.py"
        ).is_file(),
        "source_content_hashes_not_run_preopen": True,
        "test_outcome_rows_zero": (
            cfg["preopen"]["test_outcome_rows_read"] == 0
        ),
        "test_not_materialized": (
            cfg["preopen"]["test_materialized"] is False
        ),
        "holdout_unconsumed": (
            cfg["preopen"]["holdout_consumed"] is False
        ),
        "g2_not_evaluated": cfg["preopen"]["formal_g2"] == "NOT_EVALUATED",
    }

    failed = [name for name, passed in checks.items() if not bool(passed)]
    payload = {
        "phase": "F3.4g-2f",
        "component": "DGEN_JOINT_PIPELINE",
        "status": "PASS" if not failed else "FAIL",
        "preopen_gate": "PASS" if not failed else "FAIL",
        "real_test_runner_implemented": True,
        "strict_test_households": len(strict_test),
        "test_outcome_source_files_opened": [],
        "test_outcome_rows_read": 0,
        "test_materialized": False,
        "positive_authorization_issued": False,
        "holdout_consumed": False,
        "formal_g2": "NOT_EVALUATED",
        "checks": {name: bool(value) for name, value in checks.items()},
        "failed": failed,
        "overlay_scope": {
            "expected_count": len(expected_scope),
            "actual_count": len(actual_scope),
            "missing": sorted(expected_scope - actual_scope),
            "unexpected": sorted(actual_scope - expected_scope),
        },
        "next_step_if_pass": (
            "COMMIT_THEN_ISSUE_SINGLE_USE_COMMIT_BOUND_TEST_AUTHORIZATION"
        ),
    }
    print(json.dumps(payload, indent=2, sort_keys=True))
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
