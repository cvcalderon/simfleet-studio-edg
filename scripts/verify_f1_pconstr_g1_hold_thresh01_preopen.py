#!/usr/bin/env python3
from __future__ import annotations

import csv
import json
import subprocess
from decimal import Decimal
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
PARENT = "2b72fce94deae889e85953bdc8c142e91ae6b4a9"
T = Decimal("0.0815667541845037")

CFG = ROOT / "configs/f1/f1_pconstr_g1_hold_thresh01_preopen_v1.yaml"
OUT = ROOT / "docs/F1_PCONSTR_G1_HOLDOUT_THRESHOLDS_v1.csv"
SOURCE = ROOT / "docs/F1_PCONSTR_G1_THRESHOLDS_v1.csv"
MREAL = ROOT / "configs/f1/f1_pconstr_g1_hold_mreal01_main_freeze_v1.yaml"
FILELIST = ROOT / "docs/F1_PCONSTR_G1_HOLD_THRESH01_OVERLAY_FILELIST_v1.txt"
CHECKSUMS = ROOT / "docs/F1_PCONSTR_G1_HOLD_THRESH01_OVERLAY_CHECKSUMS_v1.sha256"

EXPECTED_TAUS = {
    "ACTIVITY_BY_AGE": Decimal("0.07293353416541049"),
    "LICENSE_BY_AGE_SEX": Decimal("0.0815667541845037"),
    "HH_CAR_STOCK_BY_SIZE": Decimal("0.0660999637102583"),
    "HH_BIKE_EBIKE_STOCK_BY_SIZE": Decimal("0.07409481595332659"),
}


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def source_has_exact_tau(family: str, value: Decimal) -> bool:
    text = SOURCE.read_text(encoding="utf-8")
    return family in text and format(value, "f") in text


def main() -> int:
    cfg = yaml.safe_load(CFG.read_text(encoding="utf-8"))
    mreal = yaml.safe_load(MREAL.read_text(encoding="utf-8"))

    checks: dict[str, bool] = {}
    checks["branch_main"] = git("branch", "--show-current") == "main"
    checks["parent_head"] = git("rev-parse", "HEAD") == PARENT
    checks["origin_main_parent"] = git("rev-parse", "origin/main") == PARENT
    checks["no_staged_changes"] = git("diff", "--cached", "--name-only") == ""
    checks["mreal_frozen"] = mreal.get("status_after_commit") == "HOLD_MREAL_001_RESOLVED_FROZEN"
    checks["source_threshold_artifact_exists"] = SOURCE.is_file()

    for family, value in EXPECTED_TAUS.items():
        checks[f"source_tau_{family}"] = source_has_exact_tau(family, value)

    source_max = max(EXPECTED_TAUS.values())
    checks["max_rule_exact"] = source_max == T
    checks["config_threshold_exact"] = (
        Decimal(cfg["threshold_transfer_rule"]["numeric_value"]) == T
    )
    checks["cal_not_reopened"] = cfg["boundaries"]["cal_reopened"] is False
    checks["test_not_reopened"] = cfg["boundaries"]["mid_test_reopened"] is False
    checks["holdout_unacquired"] = cfg["boundaries"]["holdout_1000A_1035_acquired"] is False
    checks["holdout_unread"] = cfg["boundaries"]["holdout_1000A_1035_values_read"] is False
    checks["holdout_not_authorized"] = cfg["boundaries"]["holdout_1000A_1035_authorized"] is False
    checks["no_composite_score"] = cfg["decision_rule"]["no_composite_score"] is True
    checks["both_metrics_required"] = cfg["decision_rule"]["pass_requires_all_decision_metrics"] is True
    checks["g1_open"] = cfg["boundaries"]["G1"] == "OPEN"
    checks["g2_closed"] = cfg["boundaries"]["G2"] == "PASS_CLOSED_DO_NOT_REOPEN"

    with OUT.open(newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    by_id = {row["metric_id"]: row for row in rows}
    checks["threshold_csv_three_metrics"] = len(rows) == 3
    for metric in ("G1-HOLD-SEN-BERLIN-TVD", "G1-HOLD-SEN-BEZ-WTVD"):
        checks[f"{metric}_threshold_exact"] = Decimal(by_id[metric]["threshold"]) == T
        checks[f"{metric}_decision_role"] = by_id[metric]["role"] == "DECISION"
        checks[f"{metric}_comparison_exact"] = by_id[metric]["comparison"] == "LESS_THAN_OR_EQUAL"
    checks["bez_max_report_only"] = by_id["G1-HOLD-SEN-BEZ-MAX"]["role"] == "REPORT_ONLY"

    expected_paths = {
        line.strip()
        for line in FILELIST.read_text(encoding="utf-8").splitlines()
        if line.strip()
    }
    status_paths = {
        line[3:]
        for line in git("status", "--porcelain", "--untracked-files=all").splitlines()
        if line
    }
    checks["overlay_scope_exact"] = status_paths == expected_paths

    checksum_result = subprocess.run(
        ["sha256sum", "-c", str(CHECKSUMS.relative_to(ROOT))],
        cwd=ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    checks["overlay_checksums_pass"] = checksum_result.returncode == 0

    failed = [key for key, passed in checks.items() if not passed]
    result = {
        "phase": "F1-P_CONSTR-G1-HOLD-THRESH-001 PREOPEN",
        "parent": PARENT,
        "threshold": format(T, "f"),
        "rule": "MAX_FROZEN_CAL_TVD_MATERIALITY_TAU_V1",
        "checks": checks,
        "failed": failed,
        "controlled_state_after_commit": {
            "HOLD_MREAL_001": "RESOLVED_FROZEN",
            "HOLD_THRESH_001": "RESOLVED_FROZEN",
            "holdout_1000A_1035_acquired": False,
            "holdout_1000A_1035_values_read": False,
            "holdout_1000A_1035_authorized": False,
            "G1": "OPEN",
            "G2": "PASS_CLOSED_DO_NOT_REOPEN",
        },
        "next_step_if_pass": "COMMIT_AND_PUSH_HOLD_THRESH01_THEN_SEPARATE_COMMIT_BOUND_HOLDOUT_AUTHORIZATION_PREOPEN",
        "status": "PASS" if not failed else "FAIL",
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
