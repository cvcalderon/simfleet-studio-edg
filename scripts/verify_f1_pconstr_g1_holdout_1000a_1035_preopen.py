#!/usr/bin/env python3
from __future__ import annotations

import ast
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import yaml

PARENT = "e2cd5e4445b3c75af865d4a1d43509a0b7953b48"
SELECTED = "P_CONSTR_RMIN_V2_HD_U"

FROZEN_HASHES = {
    "configs/f1/f1_pconstr_cal01_main_freeze_v1.yaml": "beb700de8fb57e561c8d19a2a26fbf073250fa39bc888393a2e993264cf1c1cc",
    "docs/F1_PCONSTR_CAL01_SELECTION_v1.json": "d2097d28924b058b851c3a3e9a36af4561e2c77af090335d82002a3358f374f9",
    "docs/F1_PCONSTR_G1_THRESHOLDS_v1.csv": "c910626c55dd52bf915390425dbf058e28ca1a9262722afed932c64ba2586ffd",
    "docs/F1_PCONSTR_CAL01_MAIN_AUDIT_v1.json": "991f0d8cc1fc41758ef8fb8171b6d30bae7c4a731253c234fee0634937d9a7e8",
    "configs/f1/f1_pconstr_impl03_candidates_v1.yaml": "5d27d6d7cb39b8363d5e5fe11bf31cc0ed4aec3c3ef1d467e0b3f5761c0909ae",
}

OVERLAY_FILES = [
    "configs/f1/f1_pconstr_g1_holdout_1000a_1035_preopen_v1.yaml",
    "docs/F1_PCONSTR_G1_HOLDOUT_1000A_1035_AUTHORIZATION_TEMPLATE_v1.json",
    "docs/F1_PCONSTR_G1_HOLDOUT_1000A_1035_BLOCKERS_v1.json",
    "docs/F1_PCONSTR_G1_HOLDOUT_1000A_1035_CONTRACT_SNAPSHOT_v1.json",
    "docs/F1_PCONSTR_G1_HOLDOUT_1000A_1035_METRIC_CONTRACT_v1.md",
    "docs/F1_PCONSTR_G1_HOLDOUT_1000A_1035_OVERLAY_CHECKSUMS_v1.sha256",
    "docs/F1_PCONSTR_G1_HOLDOUT_1000A_1035_OVERLAY_FILELIST_v1.txt",
    "docs/F1_PCONSTR_G1_HOLDOUT_1000A_1035_PREOPEN_v1.md",
    "scripts/verify_f1_pconstr_g1_holdout_1000a_1035_preopen.py",
    "src/simfleet_edg/population/senior_holdout_metrics.py",
    "tests/test_f1_pconstr_g1_holdout_1000a_1035_preopen.py",
]

FORBIDDEN_IO_NAMES = {
    "open", "read_csv", "read_excel", "read_parquet", "read_json", "read_text", "read_bytes",
    "urlopen", "get", "post", "request", "download", "ZipFile",
}


def git(repo: Path, *args: str) -> str:
    return subprocess.check_output(["git", "-C", str(repo), *args], text=True).strip()


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def forbidden_io_calls(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name):
                name = func.id
            elif isinstance(func, ast.Attribute):
                name = func.attr
            else:
                continue
            if name in FORBIDDEN_IO_NAMES:
                found.append(name)
    return sorted(set(found))


def main() -> int:
    repo = Path.cwd().resolve()
    cfg = yaml.safe_load((repo / "configs/f1/f1_pconstr_g1_holdout_1000a_1035_preopen_v1.yaml").read_text())
    auth = json.loads((repo / "docs/F1_PCONSTR_G1_HOLDOUT_1000A_1035_AUTHORIZATION_TEMPLATE_v1.json").read_text())
    blockers = json.loads((repo / "docs/F1_PCONSTR_G1_HOLDOUT_1000A_1035_BLOCKERS_v1.json").read_text())

    changed_lines = list(filter(None, git(repo, "status", "--porcelain").splitlines()))
    changed_paths = sorted(line[3:] for line in changed_lines)
    staged = git(repo, "diff", "--cached", "--name-only").splitlines()

    checks: dict[str, bool] = {}
    checks["branch_main"] = git(repo, "branch", "--show-current") == "main"
    checks["parent_head"] = git(repo, "rev-parse", "HEAD") == PARENT
    checks["origin_main_parent"] = git(repo, "rev-parse", "origin/main") == PARENT
    checks["no_staged_changes"] = staged == []
    checks["overlay_scope_exact"] = set(changed_paths) == set(OVERLAY_FILES)

    manifest_ok = True
    for line in (repo / "docs/F1_PCONSTR_G1_HOLDOUT_1000A_1035_OVERLAY_CHECKSUMS_v1.sha256").read_text().splitlines():
        expected, rel = line.split(maxsplit=1)
        if sha256(repo / rel.strip()) != expected:
            manifest_ok = False
    checks["overlay_checksums_pass"] = manifest_ok

    frozen_checks = {rel: (repo / rel).is_file() and sha256(repo / rel) == digest for rel, digest in FROZEN_HASHES.items()}
    checks["frozen_upstream_hashes_exact"] = all(frozen_checks.values())

    selection = json.loads((repo / "docs/F1_PCONSTR_CAL01_SELECTION_v1.json").read_text())
    main_freeze = yaml.safe_load((repo / "configs/f1/f1_pconstr_cal01_main_freeze_v1.yaml").read_text())
    impl03 = yaml.safe_load((repo / "configs/f1/f1_pconstr_impl03_candidates_v1.yaml").read_text())

    checks["selected_candidate_frozen_exact"] = selection.get("selected_candidate") == SELECTED
    checks["g1_thresholds_frozen_upstream"] = all(
        "FROZEN" in line for line in (repo / "docs/F1_PCONSTR_G1_THRESHOLDS_v1.csv").read_text().splitlines()[1:]
    )
    checks["cal_closed_no_reopen"] = cfg["frozen_upstream"]["cal01_status"] == "CLOSED_FROZEN" and cfg["frozen_upstream"]["cal_reopen"] == "FORBIDDEN"
    checks["test_closed_no_reopen"] = cfg["frozen_upstream"]["mid_test_reopen"] == "FORBIDDEN" and cfg["boundaries"]["mid_test_read"] is False

    checks["holdout_unread"] = cfg["holdout_identity"]["source_values_status"] == "UNACQUIRED_UNREAD" and cfg["boundaries"]["holdout_1000A_1035_values_read"] is False
    checks["holdout_unacquired"] = cfg["boundaries"]["holdout_1000A_1035_acquired"] is False
    checks["holdout_not_authorized"] = cfg["holdout_identity"]["source_value_io_authorized"] is False and cfg["holdout_authorization"]["authorized"] is False
    checks["authorization_template_negative"] = auth["authorized"] is False and auth["holdout_value_io_authorized"] is False
    checks["authorization_template_unbound"] = auth["required_preholdout_commit"] is None

    expected_categories = [
        "SINGLE_SENIOR_HOUSEHOLD", "TWO_PERSON_ALL_SENIOR_HOUSEHOLD",
        "MULTIPERSON_ALL_SENIOR_HOUSEHOLD", "SENIOR_AND_YOUNGER_HOUSEHOLD", "NO_SENIOR_HOUSEHOLD",
    ]
    checks["five_leaf_categories_exact"] = cfg["metric_universe"]["leaf_categories"] == expected_categories
    checks["senior_definition_exact"] = cfg["metric_universe"]["senior_definition"] == "AGE_YEARS_GTE_65"
    checks["metric_ids_exact"] = (
        cfg["metric_contract"]["berlin_tvd"]["id"] == "G1-HOLD-SEN-BERLIN-TVD"
        and cfg["metric_contract"]["bezirk_wtvd"]["id"] == "G1-HOLD-SEN-BEZ-WTVD"
        and cfg["metric_contract"]["bezirk_max"]["id"] == "G1-HOLD-SEN-BEZ-MAX"
        and cfg["metric_contract"]["bezirk_max"]["role"] == "REPORT_ONLY"
    )
    checks["complete_support_fail_closed"] = cfg["metric_contract"]["completeness_policy"] == "ALL_5_LEAVES_NUMERIC_FOR_ALL_12_BEZIRKE_ELSE_DECISION_INDETERMINATE" and cfg["metric_contract"]["imputation"] == "FORBIDDEN"

    metric_module = repo / "src/simfleet_edg/population/senior_holdout_metrics.py"
    io_calls = forbidden_io_calls(metric_module)
    checks["metric_module_io_free"] = io_calls == []

    checks["m_scale_frozen_as_required_realization"] = cfg["validation_realization"]["scale_id"] == "M" and cfg["validation_realization"]["role"] == "PRIMARY_VALIDATION_BENCHMARK"
    checks["seed_schedule_inherited_exact"] = (
        cfg["validation_realization"]["candidate_master_seed"] == impl03["seeds"]["candidate_master_seed"] == 20261005
        and cfg["validation_realization"]["h6_master_seed"] == impl03["seeds"]["h6_master_seed"] == 20261004
        and cfg["validation_realization"]["holdout_metric_randomness"] == "NONE"
    )

    blocker_map = {b["id"]: b for b in blockers["blockers"]}
    checks["hold_thresh_001_open"] = blocker_map["HOLD-THRESH-001"]["blocking"] is True and blocker_map["HOLD-THRESH-001"]["resolved"] is False
    checks["hold_mreal_001_open"] = blocker_map["HOLD-MREAL-001"]["blocking"] is True and blocker_map["HOLD-MREAL-001"]["resolved"] is False
    checks["no_numeric_senior_threshold_frozen"] = cfg["decision_threshold_status"]["status"] == "BLOCKED_PRE_HOLDOUT" and cfg["decision_threshold_status"]["implicit_reuse_of_any_existing_tau"] == "FORBIDDEN"

    checks["g1_open"] = cfg["boundaries"]["G1"] == main_freeze["boundaries"]["G1"] == "OPEN"
    checks["g2_closed"] = cfg["boundaries"]["G2"] == main_freeze["boundaries"]["G2"] == "PASS_CLOSED_DO_NOT_REOPEN"
    checks["plr_closed"] = cfg["boundaries"]["spatial_plr_allocation"] is False
    checks["f3_closed"] = cfg["boundaries"]["f3_modified"] is False

    failed = [k for k, v in checks.items() if not v]
    out = {
        "phase": "F1-P_CONSTR-G1-HOLDOUT-1000A-1035 PREOPEN",
        "parent": PARENT,
        "checks": checks,
        "frozen_upstream_hash_checks": frozen_checks,
        "metric_module_forbidden_io_calls": io_calls,
        "changed_paths": changed_paths,
        "open_blockers": ["HOLD-THRESH-001", "HOLD-MREAL-001"],
        "holdout_value_io_authorized": False,
        "failed": failed,
        "status": "PASS" if not failed else "FAIL",
        "next_step_if_pass": "COMMIT_AND_PUSH_PREOPEN_THEN_RESOLVE_HOLD_THRESH_001_AND_HOLD_MREAL_001_WITHOUT_HOLDOUT_VALUES",
    }
    print(json.dumps(out, indent=2, sort_keys=True))
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
