from __future__ import annotations

import argparse
import csv
import hashlib
import json
import subprocess
from pathlib import Path

ROOT = Path.cwd()
PARENT = "f595bbd26eb895b3b39ca5fcb2f12ce61acf4856"
FILELIST = ROOT / "docs/F3_4D2A_OVERLAY_FILELIST_v1.txt"


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], text=True).rstrip("\n")


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def checksums_ok(run: Path) -> bool:
    for line in (run / "checksums.sha256").read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        digest, name = line.split(maxsplit=1)
        if sha256(run / name.strip()) != digest:
            return False
    return True


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", type=Path, required=True)
    args = parser.parse_args()
    run = args.run_dir.resolve()

    manifest = json.loads((run / "run_manifest.json").read_text(encoding="utf-8"))
    artifacts = read_csv(run / "candidate_artifact_validation.csv")
    primary = read_csv(run / "synthetic_primary_metrics.csv")
    guardrails = read_csv(run / "synthetic_guardrails.csv")
    validation = read_csv(run / "validation.csv")
    bootstrap = json.loads(
        (run / "synthetic_bootstrap_check.json").read_text(encoding="utf-8")
    )
    crn = json.loads((run / "crn_validation.json").read_text(encoding="utf-8"))

    status_lines = [x for x in git("status", "--porcelain").splitlines() if x]
    scope = {x[3:] for x in status_lines}
    expected_scope = {
        x.strip()
        for x in FILELIST.read_text(encoding="utf-8").splitlines()
        if x.strip()
    }

    checks = {
        "head_exact_parent": git("rev-parse", "HEAD") == PARENT,
        "branch_main": git("branch", "--show-current") == "main",
        "ahead_zero": git("rev-list", "--count", "origin/main..HEAD") == "0",
        "behind_zero": git("rev-list", "--count", "HEAD..origin/main") == "0",
        "no_staged_changes": git("diff", "--cached", "--name-only") == "",
        "overlay_scope_exact": scope == expected_scope,
        "runbundle_checksums_pass": checksums_ok(run),
        "run_status_pass": manifest.get("status") == "PASS",
        "execution_mode_exact": manifest.get("execution_mode")
        == "SYNTHETIC_TRAIN_PREOPEN",
        "component_activity_chain": manifest.get("component") == "DG_ACTIVITY_CHAIN",
        "candidate_artifacts_6": manifest.get("candidate_artifacts") == 6,
        "artifact_validation_rows_6": len(artifacts) == 6,
        "artifact_validation_all_pass": all(r["status"] == "PASS" for r in artifacts),
        "synthetic_primary_rows_6": len(primary) == 6,
        "synthetic_guardrail_rows_18": len(guardrails) == 18,
        "synthetic_only_primary": all(r["synthetic_only"] == "True" for r in primary),
        "synthetic_only_guardrails": all(
            r["synthetic_only"] == "True" for r in guardrails
        ),
        "bootstrap_pass": bootstrap.get("status") == "PASS",
        "crn_pass": crn.get("status") == "PASS"
        and crn.get("same_context_same_seed") is True,
        "validation_all_pass": bool(validation)
        and all(r["status"] == "PASS" for r in validation),
        "candidate_selection_none": manifest.get("candidate_selection") == "NONE",
        "cal_read_false": manifest.get("cal_read_performed") is False,
        "cal_files_empty": manifest.get("cal_files_opened") == [],
        "cal_rows_zero": manifest.get("cal_rows_read") == 0,
        "real_cal_not_authorized": manifest.get("real_cal_open_authorized") is False,
        "test_rows_zero": manifest.get("test_rows_read") == 0,
        "test_not_authorized": manifest.get("test_open_authorized") is False,
        "next_component_not_authorized": manifest.get(
            "next_component_authorized"
        )
        is False,
        "g2_not_evaluated": manifest.get("formal_g2") == "NOT_EVALUATED",
    }
    failed = [k for k, v in checks.items() if not v]
    result = {
        "phase": "F3.4d-2a",
        "component": "DG_ACTIVITY_CHAIN",
        "status": "PASS" if not failed else "FAIL",
        "preopen_gate": "PASS" if not failed else "FAIL",
        "candidate_artifacts": manifest.get("candidate_artifacts"),
        "candidate_selection": manifest.get("candidate_selection"),
        "cal_read_performed": manifest.get("cal_read_performed"),
        "cal_rows_read": manifest.get("cal_rows_read"),
        "real_cal_open_authorized": False,
        "test_rows_read": manifest.get("test_rows_read"),
        "test_open_authorized": False,
        "formal_g2": "NOT_EVALUATED",
        "next_step_if_pass": "COMMIT_PREOPEN_THEN_PREPARE_REAL_CAL_RUNNER_PREOPEN",
        "checks": checks,
        "failed": failed,
        "overlay_scope": {
            "expected_count": len(expected_scope),
            "actual_count": len(scope),
            "missing": sorted(expected_scope - scope),
            "unexpected": sorted(scope - expected_scope),
        },
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
