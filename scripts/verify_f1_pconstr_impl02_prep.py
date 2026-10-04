#!/usr/bin/env python3
"""PRE-COMMIT verifier for F1-P_CONSTR-IMPL-02."""

from __future__ import annotations

import argparse
import json
import subprocess
import time
from pathlib import Path
from typing import Any

import yaml

from simfleet_edg.repro.f1_pconstr_impl02_scale_h6 import build_impl02_summary


def _git(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=root, check=True, capture_output=True, text=True
    ).stdout.strip()


def _compare_expected(summary: dict[str, Any], expected: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    if summary["full_h6_households_by_bezirk"] != expected["full_h6_households_by_bezirk"]:
        failures.append("full_h6_households_by_bezirk")
    if summary["full_h6_households_berlin"] != 28343:
        failures.append("full_h6_households_berlin")
    for scale_id, expected_scale in expected["scales"].items():
        observed = summary["scales"][scale_id]
        for key, value in expected_scale.items():
            if observed[key] != value:
                failures.append(f"{scale_id}.{key}: observed={observed[key]!r} expected={value!r}")
        for invariant in [
            "structural_zero_violations",
            "divisibility_violations_sizes_1_to_5",
        ]:
            if observed[invariant] != 0:
                failures.append(f"{scale_id}.{invariant}")
        for invariant in [
            "all_bezirk_targets_exact",
            "h6_household_count_exact",
            "h6_person_count_exact",
            "h6_all_at_least_six",
        ]:
            if observed[invariant] is not True:
                failures.append(f"{scale_id}.{invariant}")
        if observed["h6_persons_materialized"] != observed["p6_persons_berlin"]:
            failures.append(f"{scale_id}.h6_materialized_person_total")
    return failures


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--config",
        default="configs/f1/f1_pconstr_impl02_scale_h6_v1.yaml",
    )
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[1]
    config_path = root / args.config
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    required_parent = str(config["required_parent_commit"])

    status_lines = [line for line in _git(root, "status", "--porcelain").splitlines() if line]
    changed_paths = sorted(line[3:] for line in status_lines)
    allowed_paths = {
        "configs/f1/f1_pconstr_impl02_scale_h6_v1.yaml",
        "docs/F1_PCONSTR_IMPL02_EXECUTION_INSTRUCTIONS_v1.md",
        "docs/F1_PCONSTR_IMPL02_IMPLEMENTATION_NOTE_v1.md",
        "docs/F1_PCONSTR_IMPL02_OVERLAY_CHECKSUMS_v1.sha256",
        "docs/F1_PCONSTR_IMPL02_OVERLAY_FILELIST_v1.txt",
        "docs/F1_PCONSTR_IMPL02_PREOPEN_v1.md",
        "scripts/verify_f1_pconstr_impl02_prep.py",
        "src/simfleet_edg/population/scale_projection.py",
        "src/simfleet_edg/population/six_plus.py",
        "src/simfleet_edg/repro/f1_pconstr_impl02_scale_h6.py",
        "tests/test_f1_pconstr_impl02_config.py",
        "tests/test_f1_pconstr_scale_projection.py",
        "tests/test_f1_pconstr_six_plus.py",
    }

    checks: list[dict[str, Any]] = []

    def add(name: str, passed: bool, detail: Any) -> None:
        checks.append({"check": name, "pass": bool(passed), "detail": detail})

    head = _git(root, "rev-parse", "HEAD")
    branch = _git(root, "branch", "--show-current")
    staged = _git(root, "diff", "--cached", "--name-only")
    add("parent_head", head == required_parent, head)
    add("branch_main", branch == "main", branch)
    add("no_staged_changes", staged == "", staged.splitlines() if staged else [])
    add("overlay_scope_only", set(changed_paths).issubset(allowed_paths), changed_paths)
    f3_modified = any(
        path.startswith("configs/f3/") or "/f3_" in path for path in changed_paths
    )
    add("f3_not_modified", not f3_modified, changed_paths)

    start = time.perf_counter()
    summary = build_impl02_summary(root, config_path)
    elapsed = time.perf_counter() - start
    failures = _compare_expected(summary, config["expected"])
    add("reference_persons", summary["reference_persons"] == 3532081, summary["reference_persons"])
    add("anchors_exact", not failures, failures)
    add("calibration_unread", config["boundaries"]["calibration_read"] is False, False)
    add(
        "mid_test_unread_by_impl02",
        config["boundaries"]["mid_test_read_by_impl02"] is False,
        False,
    )
    add(
        "holdout_1000A_1035_unread",
        config["boundaries"]["holdout_1000A_1035_read"] is False,
        False,
    )
    add(
        "donor_materialization_deferred",
        config["boundaries"]["donor_materialization"] is False,
        False,
    )
    add("g1_open", config["boundaries"]["G1"] == "OPEN", config["boundaries"]["G1"])
    add(
        "g2_closed",
        config["boundaries"]["G2"] == "PASS_CLOSED_DO_NOT_REOPEN",
        config["boundaries"]["G2"],
    )

    failed = [check["check"] for check in checks if not check["pass"]]
    payload = {
        "verifier": "F1-P_CONSTR-IMPL-02 PRE-COMMIT",
        "status": "PASS" if not failed else "FAIL",
        "parent": head,
        "changed_paths": changed_paths,
        "elapsed_seconds": elapsed,
        "checks": checks,
        "failed": failed,
        "summary": summary,
    }
    print(json.dumps(payload, indent=2, sort_keys=True))
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
