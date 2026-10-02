from __future__ import annotations

import argparse
import csv
import hashlib
import json
import subprocess
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
PARENT = "5913f9604378cf2356a9251accf59105c51e9163"
CFG = ROOT / "configs/f3/f3_4g1_joint_cal_contract_freeze_v1.yaml"
REG = ROOT / "configs/f3/f3_4g1_joint_pipeline_registry_v1.json"
MATRIX = ROOT / "docs/F3_4G1_JOINT_METRIC_MATRIX_v1.csv"
WITNESS = ROOT / "docs/F3_4G1_PRIMARY_EVIDENCE_WITNESS_v1.csv"
FILELIST = ROOT / "docs/F3_4G1_OVERLAY_FILELIST_v1.txt"
CHECKSUMS = ROOT / "docs/F3_4G1_OVERLAY_CHECKSUMS_v1.sha256"


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).rstrip("\n")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def status_scope() -> set[str]:
    output = git("status", "--short")
    return {line[3:] for line in output.splitlines() if line}


def verify_sha_manifest(base: Path, manifest_path: Path) -> bool:
    for line in manifest_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        expected, rel = line.split(maxsplit=1)
        path = base / rel.strip()
        if not path.is_file() or sha256(path) != expected:
            return False
    return True


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.parse_args()

    cfg = yaml.safe_load(CFG.read_text(encoding="utf-8"))
    reg = json.loads(REG.read_text(encoding="utf-8"))

    with MATRIX.open(newline="", encoding="utf-8") as handle:
        matrix = {row["metric_id"]: row for row in csv.DictReader(handle)}
    with WITNESS.open(newline="", encoding="utf-8") as handle:
        witnesses = list(csv.DictReader(handle))

    expected_scope = set(FILELIST.read_text(encoding="utf-8").splitlines())
    scope = status_scope()

    cal_root = ROOT / cfg["cal_access"]["root"]
    cal_exists = all(
        (cal_root / name).is_file()
        for name in cfg["cal_access"]["allowed_files"]
    )

    witness_hashes = {
        name: (
            ROOT / data["path"]
        ).is_file()
        and sha256(ROOT / data["path"]) == data["sha256"]
        for name, data in cfg["frozen_component_witnesses"].items()
    }

    selected = [row["artifact_id"] for row in reg["selected_pipeline"]]
    references = [row["artifact_id"] for row in reg["all_reference_pipeline"]]

    checks = {
        "head_exact_parent": git("rev-parse", "HEAD") == PARENT,
        "branch_main": git("branch", "--show-current") == "main",
        "ahead_zero": git("rev-list", "--count", "origin/main..HEAD") == "0",
        "behind_zero": git("rev-list", "--count", "HEAD..origin/main") == "0",
        "no_staged_changes": git("diff", "--cached", "--name-only") == "",
        "overlay_scope_exact": scope == expected_scope,
        "static_checksums_pass": verify_sha_manifest(ROOT, CHECKSUMS),
        "all_five_freeze_witness_hashes_exact": all(witness_hashes.values()),
        "selected_pipeline_exact": selected == [
            "DG_PARTICIPATION::PART_A::PA1",
            "DG_TRIP_COUNT::COUNT_REF::REFERENCE",
            "DG_ACTIVITY_CHAIN::CHAIN_A::CHA2",
            "TIME_B_TB2",
            "DIST_REF_REFERENCE",
        ],
        "reference_pipeline_exact": references == [
            "DG_PARTICIPATION::PART_REF::REFERENCE",
            "DG_TRIP_COUNT::COUNT_REF::REFERENCE",
            "DG_ACTIVITY_CHAIN::CHAIN_REF::REFERENCE",
            "TIME_REF_REFERENCE",
            "DIST_REF_REFERENCE",
        ],
        "cal_files_exist_without_content_read": cal_exists,
        "cal_rows_zero": cfg["cal_access"]["rows_read_in_f3_4g1"] == 0,
        "future_cal_total_6341": (
            cfg["cal_access"]["expected_total_physical_rows_if_opened_once_each"]
            == 6341
        ),
        "replicates_32": cfg["joint_generation"]["stochastic_replicates"] == 32,
        "crn": cfg["joint_generation"]["common_random_numbers"] is True,
        "same_seed_schedule": (
            cfg["joint_generation"]["same_seed_schedule_across_pipelines"] is True
        ),
        "proper_scores_not_redefined": (
            cfg["primary_evidence"][
                "recompute_proper_scores_on_propagated_generated_state"
            ]
            is False
        ),
        "five_primary_witnesses": len(witnesses) == 5,
        "selected_component_not_dominated_witness": all(
            float(row["selected_minus_reference"]) <= 0.0 for row in witnesses
        ),
        "time_tvd_tolerance_exact": matrix["M2-TIME-01"]["max_worsening"] == "0.005",
        "distance_w1_joint_materiality_exact": (
            matrix["M2-DIST-01"]["max_worsening"] == "0.25"
        ),
        "distance_quantile_tolerances_exact": all(
            matrix[name]["max_worsening"] == "0.50"
            for name in ("DIST-P50", "DIST-P90", "DIST-P95")
        ),
        "distance_mean_report_only": (
            matrix["DIST-MEAN"]["decision_role"] == "REPORT_ONLY"
        ),
        "distance_sensitivity_report_only": (
            matrix["M2-DIST-02"]["decision_role"] == "REPORT_ONLY"
        ),
        "hard_invariants_zero": all(
            cfg["hard_gate"][key] == 0
            for key in (
                "selected_structural_invariant_violations_required",
                "selected_temporal_invariant_violations_required",
                "selected_nofuture_violations_required",
                "all_reference_structural_invariant_violations_required",
                "all_reference_temporal_invariant_violations_required",
                "all_reference_nofuture_violations_required",
            )
        ),
        "joint_real_cal_closed": (
            cfg["boundaries"]["joint_real_cal_open_authorized"] is False
        ),
        "joint_not_evaluated": cfg["boundaries"]["joint_gate_evaluated"] is False,
        "test_sealed": cfg["boundaries"]["test_open_authorized"] is False,
        "test_rows_zero": cfg["boundaries"]["test_rows_read"] == 0,
        "g2_not_evaluated": cfg["boundaries"]["formal_g2"] == "NOT_EVALUATED",
    }

    failed = [name for name, value in checks.items() if not bool(value)]
    payload = {
        "phase": "F3.4g-1",
        "component": "DGEN_JOINT_PIPELINE",
        "status": "PASS" if not failed else "FAIL",
        "contract_gate": "PASS" if not failed else "FAIL",
        "cal_rows_read": 0,
        "future_cal_physical_rows": 6341,
        "selected_component_count": 5,
        "reference_component_count": 5,
        "joint_real_cal_open_authorized": False,
        "test_open_authorized": False,
        "formal_g2": "NOT_EVALUATED",
        "checks": {name: bool(value) for name, value in checks.items()},
        "failed": failed,
        "overlay_scope": {
            "expected_count": len(expected_scope),
            "actual_count": len(scope),
            "missing": sorted(expected_scope - scope),
            "unexpected": sorted(scope - expected_scope),
        },
        "next_step_if_pass": "COMMIT_CONTRACT_THEN_BUILD_F3_4G2A_SYNTHETIC_PREOPEN",
    }
    print(json.dumps(payload, indent=2, sort_keys=True))
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
