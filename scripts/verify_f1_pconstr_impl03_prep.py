#!/usr/bin/env python3
"""PRE-COMMIT verifier for F1-P_CONSTR-IMPL-03."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any

import yaml

from simfleet_edg.population.candidate_materialization import HOUSEHOLD_USECOLS, PERSON_USECOLS
from simfleet_edg.repro.f1_pconstr_impl03_candidates import build_impl03_preopen_summary

REQUIRED_PARENT = "2f547ec53501245af1d605a866e19febfc5089b8"
ALLOWED_PATHS = {
    "configs/f1/f1_pconstr_impl03_candidates_v1.yaml",
    "docs/F1_PCONSTR_IMPL03_EXECUTION_INSTRUCTIONS_v1.md",
    "docs/F1_PCONSTR_IMPL03_IMPLEMENTATION_NOTE_v1.md",
    "docs/F1_PCONSTR_IMPL03_OVERLAY_CHECKSUMS_v1.sha256",
    "docs/F1_PCONSTR_IMPL03_OVERLAY_FILELIST_v1.txt",
    "docs/F1_PCONSTR_IMPL03_PREOPEN_v1.md",
    "scripts/verify_f1_pconstr_impl03_prep.py",
    "src/simfleet_edg/population/candidate_materialization.py",
    "src/simfleet_edg/population/equivalence.py",
    "src/simfleet_edg/repro/f1_pconstr_impl03_candidates.py",
    "tests/test_f1_pconstr_candidate_materialization.py",
    "tests/test_f1_pconstr_equivalence.py",
    "tests/test_f1_pconstr_impl03_config.py",
}
FORBIDDEN_MATCH_FIELDS = {
    "tripintent",
    "observed_trip_count",
    "trip_purpose",
    "purpose",
    "departure_time",
    "arrival_time",
    "chosen_mode",
    "mode_family",
    "waiting_time",
    "trip_time",
}


def _run(root: Path, *args: str) -> str:
    return subprocess.check_output(args, cwd=root, text=True).strip()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _worktree_paths(root: Path) -> list[str]:
    output = _run(root, "git", "status", "--porcelain")
    paths: list[str] = []
    for line in output.splitlines():
        if not line:
            continue
        value = line[3:]
        if " -> " in value:
            value = value.split(" -> ", 1)[1]
        paths.append(value)
    return sorted(paths)


def _check(checks: list[dict[str, Any]], name: str, passed: bool, detail: Any) -> None:
    checks.append({"check": name, "pass": bool(passed), "detail": detail})


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[1]
    config_path = root / args.config
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    checks: list[dict[str, Any]] = []

    head = _run(root, "git", "rev-parse", "HEAD")
    branch = _run(root, "git", "branch", "--show-current")
    origin = _run(root, "git", "rev-parse", "origin/main")
    staged = _run(root, "git", "diff", "--cached", "--name-only").splitlines()
    changed = _worktree_paths(root)
    _check(checks, "parent_head", head == REQUIRED_PARENT, head)
    _check(checks, "branch_main", branch == "main", branch)
    _check(checks, "origin_main_parent", origin == REQUIRED_PARENT, origin)
    _check(checks, "no_staged_changes", not staged, staged)
    _check(checks, "overlay_scope_only", set(changed) == ALLOWED_PATHS, changed)
    _check(
        checks,
        "f3_not_modified",
        not any(
            path.startswith("configs/f3/")
            or path.startswith("src/simfleet_edg/demand/")
            or path.startswith("src/simfleet_edg/evaluation/")
            or path.startswith("src/simfleet_edg/repro/f3_")
            for path in changed
        ),
        changed,
    )

    for source_name, source in config["sources"].items():
        path = root / source["path"]
        actual = _sha256(path) if path.is_file() else None
        _check(
            checks,
            f"source_hash_{source_name}",
            actual == source["sha256"],
            {"expected": source["sha256"], "observed": actual, "path": source["path"]},
        )

    loaded_fields = {value.lower() for value in (*HOUSEHOLD_USECOLS, *PERSON_USECOLS)}
    forbidden_loaded = sorted(loaded_fields.intersection(FORBIDDEN_MATCH_FIELDS))
    _check(checks, "no_mobility_outcome_match_fields", not forbidden_loaded, forbidden_loaded)

    summary = build_impl03_preopen_summary(root, config_path)
    expected_catalog = config["expected_catalog"]
    _check(checks, "catalog_exact", summary["catalog"] == expected_catalog, summary["catalog"])

    expected_s = config["expected_S"]
    _check(
        checks,
        "common_six_plus_branch",
        summary["S"]["common_six_plus_branch"] is expected_s["common_six_plus_branch"],
        summary["S"]["common_six_plus_branch"],
    )
    for variant_id, expected in expected_s.items():
        if variant_id == "common_six_plus_branch":
            continue
        observed = summary["S"]["variants"][variant_id]
        subset = {key: observed[key] for key in expected}
        _check(checks, f"S_{variant_id}_anchors", subset == expected, subset)

    expected_m = config["expected_M_plan"]
    observed_m = summary["M_plan"]
    m_subset = {key: observed_m[key] for key in expected_m}
    _check(checks, "M_plan_anchors", m_subset == expected_m, m_subset)

    ptrs_l1 = int(summary["S"]["variants"]["P_TRS_V1_FINAL"]["target_fit_l1"])
    hdu_l1 = int(summary["S"]["variants"]["P_CONSTR_RMIN_V2_HD_U"]["target_fit_l1"])
    hdw_l1 = int(summary["S"]["variants"]["P_CONSTR_RMIN_V2_HD_W"]["target_fit_l1"])
    _check(checks, "constrained_fit_same_U_W", hdu_l1 == hdw_l1, [hdu_l1, hdw_l1])
    _check(checks, "constrained_fit_better_than_ptrs_debug_anchor", hdu_l1 < ptrs_l1, [ptrs_l1, hdu_l1])

    boundary = summary["boundaries"]
    expected_boundary = config["boundaries"]
    _check(checks, "boundaries_exact", boundary == expected_boundary, boundary)
    _check(checks, "calibration_unread", boundary["calibration_read"] is False, False)
    _check(checks, "mid_test_unread_by_impl03", boundary["mid_test_read_by_impl03"] is False, False)
    _check(checks, "holdout_1000A_1035_unread", boundary["holdout_1000A_1035_read"] is False, False)
    _check(checks, "candidate_selection_deferred", boundary["candidate_selection"] is False, False)
    _check(checks, "g1_open", boundary["G1"] == "OPEN", boundary["G1"])
    _check(
        checks,
        "g2_closed",
        boundary["G2"] == "PASS_CLOSED_DO_NOT_REOPEN",
        boundary["G2"],
    )

    failed = [item["check"] for item in checks if not item["pass"]]
    result = {
        "verifier": "F1-P_CONSTR-IMPL-03 PRE-COMMIT",
        "parent": head,
        "changed_paths": changed,
        "checks": checks,
        "failed": failed,
        "summary": summary,
        "status": "PASS" if not failed else "FAIL",
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    raise SystemExit(0 if not failed else 1)


if __name__ == "__main__":
    main()
