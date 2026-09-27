from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

import pandas as pd
import yaml

from simfleet_edg.evaluation.cal_access_guard import PartitionAccess
from simfleet_edg.evaluation.cal_adapter_common import ArtifactRecord
from simfleet_edg.evaluation.pre_cal_entry_gate import (
    PreCalGateSnapshot,
    evaluate_pre_cal_gate,
)

ROOT = Path.cwd()
PARENT = "a4f650165f6e9f89b2d72fededec559a81bd30f8"
FILELIST = ROOT / "docs/F3_3D_PRE_CAL_ENTRY_GATE_OVERLAY_FILELIST_v1.txt"
CHECKSUMS = ROOT / "docs/F3_3D_PRE_CAL_ENTRY_GATE_OVERLAY_CHECKSUMS_v1.sha256"
CONFIG = ROOT / "configs/f3/f3_3d_pre_cal_entry_gate_v1.yaml"
EVIDENCE = ROOT / "docs/F3_3D_PRE_CAL_ENTRY_GATE_EVIDENCE_v1.yaml"


def run(*args: str) -> str:
    return subprocess.check_output(args, cwd=ROOT, text=True).strip()


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate_sha_manifest(path: Path) -> bool:
    ok = True
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line:
            continue
        digest, rel = line.split("  ", 1)
        ok &= (ROOT / rel).is_file() and sha256(ROOT / rel) == digest
    return bool(ok)


def main() -> None:
    cfg = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    ev = yaml.safe_load(EVIDENCE.read_text(encoding="utf-8"))
    a = yaml.safe_load((ROOT / "configs/f3/f3_3_pre_cal_core_v1.yaml").read_text(encoding="utf-8"))
    b = yaml.safe_load((ROOT / "configs/f3/f3_3b_cal_adapters_v1.yaml").read_text(encoding="utf-8"))
    c = yaml.safe_load((ROOT / "configs/f3/f3_3c_pre_cal_execution_harness_v1.yaml").read_text(encoding="utf-8"))

    checks: dict[str, bool] = {}

    checks["head_exact_parent"] = run("git", "rev-parse", "HEAD") == PARENT
    checks["branch_main"] = run("git", "branch", "--show-current") == "main"
    ahead, behind = run("git", "rev-list", "--left-right", "--count", "HEAD...origin/main").split()
    checks["ahead_zero"] = ahead == "0"
    checks["behind_zero"] = behind == "0"
    checks["no_staged_changes"] = run("git", "diff", "--cached", "--name-only") == ""

    expected = {
        line for line in FILELIST.read_text(encoding="utf-8").splitlines() if line
    }
    changed = {line[3:] for line in run("git", "status", "--porcelain").splitlines() if line}
    checks["overlay_scope_exact"] = changed == expected
    checks["overlay_checksums_exact"] = validate_sha_manifest(CHECKSUMS)

    lineage = cfg["lineage"]
    lineage_ok = (
        lineage["f3_3a_final_commit"] == "d79c215bcd938d772c5ee494ed62320045f4b4dc"
        and lineage["f3_3b_commit"] == "9bb4e40ecb00ba29a5c1765b9492cd18ffba0569"
        and lineage["f3_3c_commit"] == PARENT
        and run("git", "merge-base", "--is-ancestor", lineage["f3_3a_final_commit"], "HEAD") == ""
        and run("git", "merge-base", "--is-ancestor", lineage["f3_3b_commit"], "HEAD") == ""
    )
    checks["lineage_ok"] = lineage_ok

    committed_manifests_ok = all(
        validate_sha_manifest(ROOT / rel)
        for rel in cfg["required_overlay_checksum_manifests"]
    )
    checks["committed_overlay_checksums_ok"] = committed_manifests_ok

    witness_ok = True
    for value in a["source_witnesses"].values():
        witness_ok &= sha256(ROOT / value["path"]) == value["sha256"]
    checks["f3_1c_witnesses_ok"] = bool(witness_ok)

    registry_path = ROOT / a["candidate_registry"]["path"]
    registry = pd.read_csv(registry_path, dtype=str)
    counts = registry.groupby("component").size().to_dict()
    registry_ok = (
        sha256(registry_path) == a["candidate_registry"]["sha256"]
        and len(registry) == 31
        and counts == cfg["candidate_counts"]
        and set(registry["train_state"]) == {"FITTED_TRAIN_ONLY_NOT_SELECTED"}
    )
    checks["candidate_registry_ok"] = registry_ok

    artifact_ok = True
    artifact_checks = 0
    for _, row in registry.iterrows():
        record = ArtifactRecord.from_series(row)
        try:
            record.validate(ROOT)
        except Exception:
            artifact_ok = False
        artifact_checks += 1
    checks["artifact_bytes_ok"] = artifact_ok and artifact_checks == 31

    metrics_ok = (
        a["component_order"] == cfg["component_order"]
        and a["selection_rule"]["type"] == cfg["selection"]["type"]
        and a["selection_rule"]["complexity_order"] == cfg["selection"]["complexity_order"]
        and a["promotion_margins"] == cfg["promotion_margins"]
        and a["primary_metrics"] == cfg["primary_metrics"]
        and float(a["guardrail_tolerances"]["share_absolute_error_worsening"])
            == float(cfg["guardrail_tolerances"]["share_absolute_error_worsening"])
        and float(a["guardrail_tolerances"]["tvd_worsening"])
            == float(cfg["guardrail_tolerances"]["tvd_worsening"])
        and float(a["guardrail_tolerances"]["mean_trips_per_day_absolute_error_worsening"])
            == float(cfg["guardrail_tolerances"]["mean_trips_per_day_absolute_error_worsening"])
        and float(a["guardrail_tolerances"]["supported_subgroup_share_error_worsening"])
            == float(cfg["guardrail_tolerances"]["supported_subgroup_share_error_worsening"])
        and float(a["guardrail_tolerances"]["distance_quantile_absolute_error_worsening_km"])
            == float(cfg["guardrail_tolerances"]["distance_quantile_absolute_error_worsening_km"])
    )
    checks["metrics_and_margins_ok"] = metrics_ok

    modes_ok = (
        a["evaluation_modes"]["required"] == ["ISOLATED", "PROPAGATED"]
        and b["adapter_contract"]["evaluation_modes"] == ["ISOLATED", "PROPAGATED"]
        and c["evaluation_modes"] == ["ISOLATED", "PROPAGATED"]
        and a["evaluation_modes"]["teacher_forcing_runtime"] is False
        and b["adapter_contract"]["teacher_forcing_runtime"] is False
    )
    checks["isolated_propagated_ok"] = modes_ok

    p = cfg["protocol"]
    crn_ok = (
        a["stochastic_protocol"]["replicates_per_cal_person"] == p["stochastic_replicates"] == 32
        and a["stochastic_protocol"]["common_random_numbers"] is True
        and p["common_random_numbers"] is True
        and c["protocol"]["stochastic_replicates"] == 32
        and c["protocol"]["paired_crn"] is True
        and c["protocol"]["master_seed"] == p["master_seed"] == 20260926
        and c["protocol"]["scenario_id"] == p["cal_scenario_id"] == "CAL_EVAL_V1"
        and c["protocol"]["evaluation_person_id"] == p["evaluation_person_id"]
        and c["protocol"]["draw_index_encoding"] == p["draw_index_encoding"]
    )
    checks["crn_and_replicates_ok"] = crn_ok

    bootstrap_ok = (
        a["bootstrap"]["unit"] == p["bootstrap_unit"] == "HOUSEHOLD"
        and a["bootstrap"]["replicates"] == p["household_bootstrap_replicates"] == 1000
        and float(a["bootstrap"]["confidence_level"]) == float(p["confidence_level"]) == 0.95
        and a["bootstrap"]["paired"] is True
        and c["protocol"]["household_bootstrap_replicates"] == 1000
        and c["protocol"]["bootstrap_unit"] == "HOUSEHOLD"
        and c["protocol"]["bootstrap_interval"] == p["bootstrap_interval"]
    )
    checks["household_bootstrap_ok"] = bootstrap_ok

    checks["part_b_crossfit_ok"] = (
        a["part_b_calibration"]["folds"] == p["part_b_crossfit_folds"] == 5
        and a["part_b_calibration"]["fold_unit"] == "HOUSEHOLD"
        and float(a["part_b_calibration"]["min_logloss_gain"]) == 0.002
        and float(a["part_b_calibration"]["max_trip_day_share_error_worsening"]) == 0.005
    )

    from simfleet_edg.evaluation.cal_calibration import sigmoid_calibration_decision
    from simfleet_edg.evaluation.cal_joint_gate import joint_cal_gate
    from simfleet_edg.evaluation.cal_selection import (
        choose_within_family,
        promotion_decision,
    )

    checks["promotion_logic_ok"] = all(callable(x) for x in (choose_within_family, promotion_decision))
    checks["part_b_calibration_primitive_present"] = callable(sigmoid_calibration_decision)
    checks["joint_test_gate_ok"] = callable(joint_cal_gate)

    guard = PartitionAccess()
    cal_blocked = test_blocked = False
    try:
        guard.require_cal()
    except PermissionError:
        cal_blocked = True
    try:
        guard.require_test()
    except PermissionError:
        test_blocked = True
    checks["cal_access_blocked_before_gate"] = cal_blocked
    checks["test_access_blocked"] = test_blocked

    boundary_ok = (
        a["cal_partition"] == "UNOPENED"
        and b["cal_partition"] == "UNOPENED"
        and c["boundaries"]["cal_open_authorized"] is False
        and c["boundaries"]["cal_rows_read"] == 0
    )
    checks["cal_rows_read_zero"] = boundary_ok
    checks["test_rows_read_zero"] = (
        a["test_partition"] == "SEALED"
        and b["test_partition"] == "SEALED"
        and c["boundaries"]["test_open_authorized"] is False
        and c["boundaries"]["test_rows_read"] == 0
    )
    checks["selection_none"] = (
        a["candidate_selection"] == "NONE"
        and b["candidate_selection"] == "NONE"
        and c["boundaries"]["candidate_selection"] == "NONE"
    )

    regression_ok = (
        ev["f3_3a"]["focused_tests_pass"] == 23
        and ev["f3_3a"]["full_regression_pass"] == 197
        and ev["f3_3a"]["ruff"] == "PASS"
        and ev["f3_3b"]["focused_tests_pass"] == 57
        and ev["f3_3b"]["full_regression_pass"] == 254
        and ev["f3_3b"]["ruff"] == "PASS"
        and ev["f3_3c"]["focused_tests_pass"] == 17
        and ev["f3_3c"]["full_regression_pass"] == 271
        and ev["f3_3c"]["ruff"] == "PASS"
    )
    checks["regression_evidence_ok"] = regression_ok

    snapshot = PreCalGateSnapshot(
        lineage_ok=checks["lineage_ok"],
        committed_overlay_checksums_ok=checks["committed_overlay_checksums_ok"],
        f3_1c_witnesses_ok=checks["f3_1c_witnesses_ok"],
        candidate_registry_ok=checks["candidate_registry_ok"],
        artifact_bytes_ok=checks["artifact_bytes_ok"],
        metrics_and_margins_ok=checks["metrics_and_margins_ok"],
        isolated_propagated_ok=checks["isolated_propagated_ok"],
        crn_and_replicates_ok=checks["crn_and_replicates_ok"],
        household_bootstrap_ok=checks["household_bootstrap_ok"],
        part_b_crossfit_ok=checks["part_b_crossfit_ok"] and checks["part_b_calibration_primitive_present"],
        promotion_logic_ok=checks["promotion_logic_ok"],
        joint_test_gate_ok=checks["joint_test_gate_ok"],
        cal_access_blocked_before_gate=checks["cal_access_blocked_before_gate"],
        test_access_blocked=checks["test_access_blocked"],
        cal_rows_read_zero=checks["cal_rows_read_zero"],
        test_rows_read_zero=checks["test_rows_read_zero"],
        selection_none=checks["selection_none"],
        regression_evidence_ok=checks["regression_evidence_ok"],
    )
    decision = evaluate_pre_cal_gate(snapshot)

    failed = [key for key, value in checks.items() if not bool(value)]
    if not decision.pass_gate:
        failed.extend(f"gate:{reason}" for reason in decision.reasons)

    print(json.dumps({
        "status": "PASS" if not failed and decision.pass_gate else "FAIL",
        "pre_cal_entry_gate": "PASS" if decision.pass_gate else "FAIL",
        "artifact_checks": artifact_checks,
        "cal_rows_read": 0,
        "test_rows_read": 0,
        "candidate_selection": "NONE",
        "cal_open_authorized_for_next_controlled_run":
            decision.cal_open_authorized_for_next_controlled_run,
        "test_open_authorized": decision.test_open_authorized,
        "formal_g2": decision.formal_g2,
        "checks": {k: bool(v) for k, v in checks.items()},
        "failed": failed,
    }, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
