"""PRE-COMMIT verifier for F1-P_CONSTR-IMPL-01."""

from __future__ import annotations

import argparse
import json
import subprocess
import time
from pathlib import Path

import yaml

from simfleet_edg.population.reconciliation import reconcile_all_bezirke, reconciliation_summary
from simfleet_edg.population.zensus_controls import (
    normalize_flat_count_zip,
    validate_fit_source_categories,
)

REQUIRED_PARENT = "15b2fa7a8a0a8dc5e8a8518a284350f2d35d0902"
ALLOWED_CHANGED_PREFIXES = (
    "configs/f1/f1_pconstr_",
    "docs/F1_PCONSTR_",
    "scripts/stage_f1_pconstr_sources.py",
    "scripts/verify_f1_pconstr_impl01_prep.py",
    "src/simfleet_edg/population/",
    "src/simfleet_edg/repro/f1_pconstr_impl01_reconcile.py",
    "tests/test_f1_pconstr_",
)


def root() -> Path:
    return Path(__file__).resolve().parents[1]


def git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=repo, check=True, capture_output=True, text=True
    ).stdout.strip()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    args = parser.parse_args()
    repo = root()
    checks: list[dict[str, object]] = []

    head = git(repo, "rev-parse", "HEAD")
    branch = git(repo, "branch", "--show-current")
    changed = [line[3:] for line in git(repo, "status", "--porcelain").splitlines() if line]
    checks.append({"check": "parent_head", "pass": head == REQUIRED_PARENT, "detail": head})
    checks.append({"check": "branch_main", "pass": branch == "main", "detail": branch})
    bad_scope = [
        path for path in changed if not any(path.startswith(prefix) for prefix in ALLOWED_CHANGED_PREFIXES)
    ]
    checks.append({"check": "overlay_scope_only", "pass": not bad_scope, "detail": bad_scope})

    config_path = args.config.resolve()
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    sources = {}
    for table_id, spec in config["sources"].items():
        path = repo / spec["path"]
        checks.append({"check": f"source_exists_{table_id}", "pass": path.is_file(), "detail": str(path)})
        if path.is_file():
            sources[table_id] = normalize_flat_count_zip(
                path, table_id=table_id, expected_sha256=spec["sha256"]
            )
    if len(sources) == len(config["sources"]):
        validate_fit_source_categories(sources)
        reconciliation_started = time.perf_counter()
        cube, audit = reconcile_all_bezirke(
            sources["1000A-3082"], sources["1000A-1029"], sources["1000A-2071"]
        )
        reconciliation_elapsed_seconds = time.perf_counter() - reconciliation_started
        summary = reconciliation_summary(cube, audit)
        for key, expected in config["expected_reconciliation"].items():
            checks.append(
                {
                    "check": f"anchor_{key}",
                    "pass": summary[key] == expected,
                    "detail": {"observed": summary[key], "expected": expected},
                }
            )
        zero_violations = int(
            (cube.loc[cube["published_value"] == 0, "fit_target_value"] != 0).sum()
        )
        checks.append(
            {"check": "published_zero_violations", "pass": zero_violations == 0, "detail": zero_violations}
        )
    else:
        summary = None
        reconciliation_elapsed_seconds = None
        checks.append(
            {
                "check": "reconciliation_executed",
                "pass": False,
                "detail": "missing sources",
            }
        )

    overall = all(bool(item["pass"]) for item in checks)
    result = {
        "verifier": "F1-P_CONSTR-IMPL-01 PRE-COMMIT",
        "status": "PASS" if overall else "FAIL",
        "parent": head,
        "changed_paths": changed,
        "reconciliation_summary": summary,
        "reconciliation_elapsed_seconds": reconciliation_elapsed_seconds,
        "checks": checks,
        "boundaries": {
            "calibration_read": False,
            "test_read": False,
            "f3_modified": False,
            "commit_authorized": False,
        },
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    raise SystemExit(0 if overall else 1)


if __name__ == "__main__":
    main()
