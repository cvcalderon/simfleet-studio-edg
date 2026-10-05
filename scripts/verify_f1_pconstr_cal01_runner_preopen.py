from __future__ import annotations

import ast
import hashlib
import json
import subprocess
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
PARENT = "2313ef1689037bcb45812e896324585d8988b4bf"
CFG = ROOT / "configs/f1/f1_pconstr_cal01_runner_preopen_v1.yaml"
FILELIST = ROOT / "docs/F1_PCONSTR_CAL01_RUNNER_OVERLAY_FILELIST_v1.txt"
CHECKSUMS = ROOT / "docs/F1_PCONSTR_CAL01_RUNNER_OVERLAY_CHECKSUMS_v1.sha256"
RUNNER = ROOT / "src/simfleet_edg/repro/f1_pconstr_cal01_runner.py"
PROTO_AUTH = ROOT / "docs/F1_PCONSTR_CAL01_AUTHORIZATION_v1.json"
EXEC_TEMPLATE = ROOT / "docs/F1_PCONSTR_CAL01_EXECUTION_AUTHORIZATION_TEMPLATE_v1.json"
FROZEN = {
    "configs/f1/f1_pconstr_cal01_preopen_v1.yaml": "7783fd713d584d8b51a2d5cfe46492e403eea0d29d50020081eb0e5320f96cb7",
    "configs/f1/f1_pconstr_cal01_authorization_v1.yaml": "b293769852601d15d04337a7d10f6ad9e1b7b340837a5a47f871658825de20ef",
    "docs/F1_PCONSTR_CAL01_AUTHORIZATION_v1.json": "d32bdbfc1fa61ee6b5348f023e2f05ea8083aac5199a7968fb06e75c25b5e679",
    "docs/F1_PCONSTR_CAL01_THRESHOLD_RULE_v1.md": "06fc136e6adb9880a74aa0fe618264fa2f77cddecdeda8de02ad7ef6168f4378",
    "src/simfleet_edg/population/calibration_evaluation.py": "11389f780efaf2755cb2b4da06feb6a57b0c35a03d24e001e0deef59b2e58ef2",
    "configs/f1/f1_pconstr_impl03_candidates_v1.yaml": "5d27d6d7cb39b8363d5e5fe11bf31cc0ed4aec3c3ef1d467e0b3f5761c0909ae",
}


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).rstrip("\n")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def checksum_manifest_ok() -> bool:
    for line in CHECKSUMS.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        expected, rel = line.split(maxsplit=1)
        path = ROOT / rel.strip()
        if not path.is_file() or sha(path) != expected:
            return False
    return True


def runner_order_ok() -> bool:
    tree = ast.parse(RUNNER.read_text(encoding="utf-8"))
    fn = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "run_controlled_cal")
    text = ast.get_source_segment(RUNNER.read_text(encoding="utf-8"), fn) or ""
    auth_pos = text.find("validate_execution_authorization")
    cal_pos = text.find("_build_cal_reference")
    stage_pos = text.find("partial.mkdir")
    return auth_pos >= 0 and cal_pos > auth_pos and stage_pos > auth_pos


def main() -> None:
    cfg = yaml.safe_load(CFG.read_text(encoding="utf-8"))
    proto = json.loads(PROTO_AUTH.read_text(encoding="utf-8"))
    template = json.loads(EXEC_TEMPLATE.read_text(encoding="utf-8"))
    expected_scope = set(FILELIST.read_text(encoding="utf-8").splitlines())
    actual_scope = {line[3:] for line in git("status", "--short").splitlines() if line}
    frozen_hashes = {rel: sha(ROOT / rel) == expected for rel, expected in FROZEN.items()}
    checks = {
        "branch_main": git("branch", "--show-current") == "main",
        "parent_head": git("rev-parse", "HEAD") == PARENT,
        "origin_main_parent": git("rev-parse", "origin/main") == PARENT,
        "no_staged_changes": git("diff", "--cached", "--name-only") == "",
        "overlay_scope_exact": actual_scope == expected_scope,
        "overlay_checksums_pass": checksum_manifest_ok(),
        "frozen_assets_hash_exact": all(frozen_hashes.values()),
        "protocol_authorization_true": proto.get("authorized") is True,
        "protocol_authorization_pending_runner": proto.get("authorization_status") == "AUTHORIZED_PENDING_RUNNER",
        "protocol_authorization_commit_exact": cfg["protocol_authorization"]["protocol_authorization_commit"] == PARENT,
        "execution_auth_external": cfg["execution_authorization"]["positive_file_must_be_external"] is True,
        "execution_template_negative": template.get("authorized") is False and template.get("cal_open_authorized") is False,
        "runner_commit_placeholder": template.get("authorized_runner_commit") == "REQUIRED_EXACT_RUNNER_COMMIT_AFTER_PREOPEN_COMMIT",
        "runner_auth_before_cal_and_staging": runner_order_ok(),
        "cal_rows_zero_preopen": cfg["preopen_boundaries"]["cal_rows_materialized_by_runner"] == 0,
        "runner_not_executed": cfg["preopen_boundaries"]["runner_executed"] is False,
        "candidate_selection_none": cfg["preopen_boundaries"]["candidate_selection"] == "NONE",
        "thresholds_not_frozen": cfg["preopen_boundaries"]["g1_thresholds_v1"] == "NOT_FROZEN",
        "test_closed": cfg["preopen_boundaries"]["mid_test_read"] is False,
        "holdout_closed": cfg["preopen_boundaries"]["holdout_1000A_1035_read"] is False,
        "plr_closed": cfg["preopen_boundaries"]["spatial_plr_allocation"] is False,
        "f3_closed": cfg["preopen_boundaries"]["f3_modified"] is False,
        "impl03_hash_exact": cfg["candidate_runbundle"]["sha256"] == "78c2a939cd7de08b048aed0cbd2a21abed73c87b68ce71860af1bbe321dd42a6",
        "bootstrap_1000": cfg["evaluation"]["bootstrap_replicates"] == 1000,
        "quantile_higher": cfg["evaluation"]["bootstrap_quantile_method"] == "higher",
        "no_composite_score": cfg["evaluation"]["no_composite_score"] is True,
    }
    failed = [name for name, ok in checks.items() if not bool(ok)]
    payload = {
        "phase": "F1-P_CONSTR-CAL-01 CAL RUNNER PREOPEN",
        "parent": PARENT,
        "status": "PASS" if not failed else "FAIL",
        "checks": {k: bool(v) for k, v in checks.items()},
        "failed": failed,
        "frozen_asset_hash_checks": frozen_hashes,
        "changed_paths": sorted(actual_scope),
        "controlled_state": cfg["preopen_boundaries"],
        "next_step_if_pass": "COMMIT_AND_PUSH_RUNNER_THEN_ISSUE_EXTERNAL_COMMIT_BOUND_EXECUTION_AUTHORIZATION_A1",
    }
    print(json.dumps(payload, indent=2, sort_keys=True))
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
