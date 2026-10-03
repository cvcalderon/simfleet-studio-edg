from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[1]
PARENT = "5992cdc34cd0e729a71e790caa15d839db99475d"
CFG = ROOT / "configs/f3/f3_4g2e_heldout_test_protocol_preopen_v1.yaml"
TEMPLATE = ROOT / "configs/f3/f3_4g2e_test_authorization_TEMPLATE_v1.json"
FILELIST = ROOT / "docs/F3_4G2E_OVERLAY_FILELIST_v1.txt"
CHECKSUMS = ROOT / "docs/F3_4G2E_OVERLAY_CHECKSUMS_v1.sha256"
METRIC_MATRIX = ROOT / "docs/F3_4G1_JOINT_METRIC_MATRIX_v1.csv"


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).rstrip("\n")


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
    template = json.loads(TEMPLATE.read_text(encoding="utf-8"))
    metric_matrix = pd.read_csv(METRIC_MATRIX)

    expected_scope = set(FILELIST.read_text(encoding="utf-8").splitlines())
    actual_scope = {line[3:] for line in git("status", "--short").splitlines() if line}

    split_cfg = cfg["heldout_split_identity"]
    split_path = ROOT / split_cfg["path"]
    split = pd.read_csv(split_path)

    full_counts = split["split"].astype(str).value_counts().to_dict()
    strict = split.loc[
        split["split_stratum"].astype(str).str.startswith(
            split_cfg["strict_rmin_rule"]["split_stratum_prefix"]
        )
    ]
    strict_counts = strict["split"].astype(str).value_counts().to_dict()

    decision = metric_matrix.loc[metric_matrix["decision_role"].ne("REPORT_ONLY")]
    report_only = metric_matrix.loc[metric_matrix["decision_role"].eq("REPORT_ONLY")]

    checks = {
        "head_exact_parent": git("rev-parse", "HEAD") == PARENT,
        "branch_main": git("branch", "--show-current") == "main",
        "ahead_zero": git("rev-list", "--count", "origin/main..HEAD") == "0",
        "behind_zero": git("rev-list", "--count", "HEAD..origin/main") == "0",
        "no_staged_changes": git("diff", "--cached", "--name-only") == "",
        "overlay_scope_exact": actual_scope == expected_scope,
        "overlay_checksums_pass": verify_overlay_checksums(),
        "metric_matrix_hash_exact": sha256_file(METRIC_MATRIX) == cfg["metric_protocol"]["metric_matrix_sha256"],
        "metrics_17": len(metric_matrix) == 17,
        "decision_metrics_14": len(decision) == 14,
        "report_only_3": len(report_only) == 3,
        "split_manifest_exists": split_path.is_file(),
        "split_manifest_hash_exact": sha256_file(split_path) == split_cfg["sha256"],
        "split_manifest_rows_1770": len(split) == 1770,
        "split_manifest_version_exact": set(split["split_manifest_version"].astype(str)) == {split_cfg["split_manifest_version"]},
        "split_seed_exact": set(split["split_seed"].astype(int)) == {int(split_cfg["split_seed"])},
        "split_unit_household": set(split["split_unit"].astype(str)) == {split_cfg["split_unit"]},
        "household_id_unique_1770": split["source_household_id"].nunique(dropna=False) == 1770,
        "full_split_counts_exact": full_counts == split_cfg["full_split_counts"],
        "strict_rmin_total_1742": len(strict) == split_cfg["strict_rmin_rule"]["total_households"],
        "strict_rmin_split_counts_exact": strict_counts == split_cfg["strict_rmin_rule"]["split_counts"],
        "test_materialization_not_required": cfg["heldout_test"]["materialized_directory_required_in_preopen"] is False,
        "materialization_deferred": cfg["heldout_test"]["materialization_deferred_until_authorized_runner"] is True,
        "test_outcome_content_rows_zero": cfg["heldout_test"]["outcome_content_rows_read_in_preopen"] == 0,
        "test_outcome_hashes_not_computed": cfg["heldout_test"]["outcome_content_hashes_computed_in_preopen"] is False,
        "test_outcome_row_counts_not_read": cfg["heldout_test"]["outcome_exact_row_counts_read_in_preopen"] is False,
        "single_use": cfg["heldout_test"]["single_use_holdout"] is True,
        "assignment_metadata_nonconsuming": cfg["heldout_test"]["split_assignment_metadata_does_not_consume_holdout"] is True,
        "rerun_forbidden_after_outcome_io": cfg["heldout_test"]["same_holdout_rerun_after_outcome_content_io"] is False,
        "replicates_32": cfg["stochastic_protocol"]["replicates"] == 32,
        "test_seed_exact": cfg["stochastic_protocol"]["master_seed"] == 20261003,
        "crn": cfg["stochastic_protocol"]["common_random_numbers"] is True,
        "selection_none": cfg["pipelines"]["candidate_selection"] == "NONE",
        "post_test_tuning_forbidden": cfg["pipelines"]["post_test_tuning"] == "FORBIDDEN",
        "tracked_template_test_negative": template["heldout_test_open_authorized"] is False,
        "tracked_template_g2_negative": template["formal_g2_evaluation_authorized"] is False,
        "preopen_test_closed": cfg["preopen_boundaries"]["test_open_authorized"] is False,
        "preopen_holdout_unconsumed": cfg["preopen_boundaries"]["holdout_consumed"] is False,
        "g2_not_evaluated": cfg["preopen_boundaries"]["formal_g2"] == "NOT_EVALUATED",
    }

    failed = [name for name, passed in checks.items() if not bool(passed)]
    payload = {
        "phase": "F3.4g-2e",
        "component": "DGEN_JOINT_PIPELINE",
        "status": "PASS" if not failed else "FAIL",
        "preopen_gate": "PASS" if not failed else "FAIL",
        "split_manifest_metadata_rows_read": len(split),
        "full_split_counts": full_counts,
        "strict_rmin_split_counts": strict_counts,
        "strict_rmin_total": len(strict),
        "test_outcome_content_rows_read": 0,
        "test_outcome_hashes_computed": False,
        "test_outcome_row_counts_read": False,
        "test_materialized": False,
        "test_open_authorized": False,
        "holdout_consumed": False,
        "formal_g2": "NOT_EVALUATED",
        "decision_metrics": len(decision),
        "report_only_metrics": len(report_only),
        "failed": failed,
        "checks": {name: bool(value) for name, value in checks.items()},
        "overlay_scope": {
            "expected_count": len(expected_scope),
            "actual_count": len(actual_scope),
            "missing": sorted(expected_scope - actual_scope),
            "unexpected": sorted(actual_scope - expected_scope),
        },
        "next_step_if_pass": "COMMIT_THEN_IMPLEMENT_F3_4G2F_TEST_RUNNER_PREOPEN",
    }
    print(json.dumps(payload, indent=2, sort_keys=True))
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
