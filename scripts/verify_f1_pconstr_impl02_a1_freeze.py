#!/usr/bin/env python3
"""Verify preserved F1-P_CONSTR-IMPL-02 A1 RunBundle for MAIN freeze."""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import zipfile
from pathlib import Path

import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[1]
CFG = ROOT / "configs/f1/f1_pconstr_impl02_a1_freeze_v1.yaml"
SCALE_SNAPSHOT = ROOT / "docs/F1_PCONSTR_IMPL02_SCALE_SUMMARY_A1_SNAPSHOT_v1.csv"
VALIDATION_SNAPSHOT = ROOT / "docs/F1_PCONSTR_IMPL02_VALIDATION_A1_SNAPSHOT_v1.csv"
FULL_PRIOR_SNAPSHOT = ROOT / "docs/F1_PCONSTR_IMPL02_FULL_H6_PRIOR_A1_SNAPSHOT_v1.csv"
FILELIST = ROOT / "docs/F1_PCONSTR_IMPL02_FREEZE_OVERLAY_FILELIST_v1.txt"
PARENT = "b60017b8233856fa365bc63d4ddca9aa47e14566"
RUN_ZIP_SHA256 = "3a22dcf88dfbd83271d8b0b65d4d3c5590431bcf8ac269fddf713c4364474b81"
REFERENCE_PERSONS = 3532081
EXPECTED_RUN_FILES = {
    "checksums.sha256",
    "config_snapshot.yaml",
    "full_scale_h6_prior.csv",
    "h6_households_L.csv",
    "h6_households_M.csv",
    "h6_households_S.csv",
    "h6_prior_L.csv",
    "h6_prior_M.csv",
    "h6_prior_S.csv",
    "manifest.json",
    "performance.csv",
    "projected_cube_L.csv",
    "projected_cube_M.csv",
    "projected_cube_S.csv",
    "run.log",
    "scale_summary.csv",
    "validation.csv",
}
EXPECTED = {
    "S": {"target": 10000, "l1": 1392907648, "p6": 685, "h6": 80, "min": 6, "max": 16, "size6": 19, "gt10": 18},
    "M": {"target": 100000, "l1": 1360353392, "p6": 6873, "h6": 802, "min": 6, "max": 25, "size6": 230, "gt10": 150},
    "L": {"target": 1000000, "l1": 1326140012, "p6": 68711, "h6": 8024, "min": 6, "max": 38, "size6": 2389, "gt10": 1537},
}
SIZE_MAP = {"PERSON01": 1, "PERSON02": 2, "PERSON03": 3, "PERSON04": 4, "PERSON05": 5}


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def verify_checksum_manifest(directory: Path, manifest_name: str) -> bool:
    manifest = directory / manifest_name
    if not manifest.is_file():
        return False
    for line in manifest.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        expected, rel = line.split(maxsplit=1)
        path = directory / rel.strip()
        if not path.is_file() or sha256_file(path) != expected:
            return False
    return True


def derive_scale(run: Path, scale: str, target: int) -> dict:
    cube = pd.read_csv(run / f"projected_cube_{scale}.csv", keep_default_na=False)
    prior = pd.read_csv(run / f"h6_prior_{scale}.csv")
    hh = pd.read_csv(run / f"h6_households_{scale}.csv")

    bezirk = cube.groupby("bezirk_code").agg(
        projected=("projected_persons", "sum"),
        target=("bezirk_target_persons", "first"),
    )
    divisibility = 0
    for code, size in SIZE_MAP.items():
        values = (
            cube.loc[cube["household_size_code"].eq(code)]
            .groupby("bezirk_code")["projected_persons"]
            .sum()
        )
        divisibility += int((values % size != 0).sum())

    l1 = int(
        (
            cube["projected_persons"].astype("int64") * REFERENCE_PERSONS
            - cube["fit_target_value"].astype("int64") * target
        )
        .abs()
        .sum()
    )
    zero_violations = int(
        (cube["published_raw"].eq("-") & cube["projected_persons"].ne(0)).sum()
    )
    p6 = int(
        cube.loc[cube["household_size_code"].eq("PERSON06UM"), "projected_persons"].sum()
    )

    return {
        "target_persons": int(cube["projected_persons"].sum()),
        "bezirk_count": int(cube["bezirk_code"].nunique()),
        "detail_cells": len(cube),
        "l1": l1,
        "p6": p6,
        "structural_zero_violations": zero_violations,
        "divisibility_violations": divisibility,
        "all_bezirk_targets_exact": bool((bezirk["projected"] == bezirk["target"]).all()),
        "h6": len(hh),
        "h6_prior": int(prior["scale_h6_households"].sum()),
        "h6_person_sum": int(hh["generated_household_size"].sum()),
        "h6_prior_person_sum": int(prior["projected_persons_6plus"].sum()),
        "h6_min": int(hh["generated_household_size"].min()),
        "h6_max": int(hh["generated_household_size"].max()),
        "h6_size6": int(hh["generated_household_size"].eq(6).sum()),
        "h6_gt10": int(hh["generated_household_size"].gt(10).sum()),
        "h6_ids_unique": bool(hh["h6_household_id"].is_unique),
        "h6_all_ge6": bool(hh["generated_household_size"].ge(6).all()),
        "h6_prior_capacity_feasible": bool(
            (prior["scale_h6_households"] <= prior["cap_households_from_persons"]).all()
        ),
        "donor_deferred": set(hh["donor_materialization_status"]) == {"DEFERRED_TO_IMPL_03"},
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--run-zip", required=True)
    args = parser.parse_args()

    run = Path(args.run_dir).expanduser().resolve()
    run_zip = Path(args.run_zip).expanduser().resolve()
    cfg = yaml.safe_load(CFG.read_text(encoding="utf-8"))
    manifest = json.loads((run / "manifest.json").read_text(encoding="utf-8"))
    run_config = yaml.safe_load((run / "config_snapshot.yaml").read_text(encoding="utf-8"))
    full_prior = pd.read_csv(run / "full_scale_h6_prior.csv")
    scale_summary = pd.read_csv(run / "scale_summary.csv")
    validation = pd.read_csv(run / "validation.csv")
    performance = pd.read_csv(run / "performance.csv")

    actual_run_files = {p.name for p in run.iterdir() if p.is_file()}
    expected_scope = set(FILELIST.read_text(encoding="utf-8").splitlines())
    actual_scope = {line[3:] for line in git("status", "--short").splitlines() if line}
    derived = {
        scale: derive_scale(run, scale, values["target"])
        for scale, values in EXPECTED.items()
    }

    checks = {
        "head_exact_parent": git("rev-parse", "HEAD") == PARENT,
        "branch_main": git("branch", "--show-current") == "main",
        "ahead_zero": git("rev-list", "--count", "origin/main..HEAD") == "0",
        "behind_zero": git("rev-list", "--count", "HEAD..origin/main") == "0",
        "no_staged_changes": git("diff", "--cached", "--name-only") == "",
        "overlay_scope_exact": actual_scope == expected_scope,
        "run_zip_hash_exact": run_zip.is_file() and sha256_file(run_zip) == RUN_ZIP_SHA256,
        "run_zip_integrity": run_zip.is_file() and zipfile.ZipFile(run_zip).testzip() is None,
        "run_files_exact": actual_run_files == EXPECTED_RUN_FILES,
        "run_checksums_pass": verify_checksum_manifest(run, "checksums.sha256"),
        "manifest_schema_exact": manifest["schema_version"] == "simfleet-edg-f1-pconstr-impl02-runbundle-v1",
        "manifest_phase_exact": manifest["phase_id"] == "F1-P_CONSTR-IMPL-02",
        "manifest_status_pass": manifest["status"] == "PASS",
        "execution_commit_exact": manifest["git"]["commit"] == PARENT,
        "execution_origin_exact": manifest["git"]["origin_main"] == PARENT,
        "execution_branch_main": manifest["git"]["branch"] == "main",
        "execution_worktree_clean": bool(manifest["git"]["worktree_clean"]),
        "algorithm_exact": run_config["scale_projection"]["algorithm_id"] == "EXACT_L1_MODULAR_ROUNDING_V1",
        "tie_break_exact": run_config["scale_projection"]["tie_break_id"] == "CANONICAL_WEIGHTED_INCREMENT_V1",
        "six_plus_policy_exact": run_config["six_plus"]["policy_id"] == "H6_COMPLETION_V1",
        "six_plus_method_exact": run_config["six_plus"]["size_method_id"] == "UNIFORM_WEAK_COMPOSITION_V1",
        "master_seed_exact": int(run_config["six_plus"]["master_seed"]) == 20261004,
        "reference_persons_exact": int(manifest["reference_persons"]) == REFERENCE_PERSONS,
        "full_h6_total_exact": int(full_prior["full_scale_h6_prior"].sum()) == 28343,
        "full_h6_role_exact": set(full_prior["role"]) == {"MODEL_FIXED_STRUCTURAL_TARGET_NOT_SOURCE_HARD"},
        "reconciled_full_p6_exact": int(full_prior["person_target_6plus_full"].sum()) == 242676,
        "semantic_difference_exact": int(full_prior["person_target_6plus_full"].sum()) - 242700 == -24,
        "scale_summary_snapshot_exact": scale_summary.equals(pd.read_csv(SCALE_SNAPSHOT)),
        "validation_snapshot_exact": validation.equals(pd.read_csv(VALIDATION_SNAPSHOT)),
        "full_prior_snapshot_exact": full_prior.equals(pd.read_csv(FULL_PRIOR_SNAPSHOT)),
        "validation_all_pass": bool(validation["status"].eq("PASS").all()),
        "performance_single_positive": len(performance) == 1 and float(performance.iloc[0]["wall_seconds"]) > 0,
        "calibration_not_read": manifest["policy"]["calibration_read"] is False,
        "mid_test_not_read_by_impl02": manifest["policy"]["mid_test_read_by_impl02"] is False,
        "holdout_not_read": manifest["policy"]["holdout_1000A_1035_read"] is False,
        "donor_not_materialized": manifest["policy"]["donor_materialization"] is False,
        "plr_not_allocated": manifest["policy"]["spatial_PLR_allocation"] is False,
        "candidates_not_materialized": manifest["policy"]["candidate_HD_U_HD_W"] is False,
        "f3_not_modified": manifest["policy"]["f3_modified"] is False,
        "g1_open": manifest["policy"]["G1"] == "OPEN",
        "g2_closed": manifest["policy"]["G2"] == "PASS_CLOSED_DO_NOT_REOPEN",
    }

    for scale, exp in EXPECTED.items():
        got = derived[scale]
        checks.update({
            f"{scale}_target_exact": got["target_persons"] == exp["target"],
            f"{scale}_bezirk_count_12": got["bezirk_count"] == 12,
            f"{scale}_cube_rows_1584": got["detail_cells"] == 1584,
            f"{scale}_l1_exact": got["l1"] == exp["l1"],
            f"{scale}_p6_exact": got["p6"] == exp["p6"],
            f"{scale}_zeros_exact": got["structural_zero_violations"] == 0,
            f"{scale}_divisibility_exact": got["divisibility_violations"] == 0,
            f"{scale}_bezirk_targets_exact": got["all_bezirk_targets_exact"],
            f"{scale}_h6_exact": got["h6"] == exp["h6"] == got["h6_prior"],
            f"{scale}_h6_person_exact": got["h6_person_sum"] == exp["p6"] == got["h6_prior_person_sum"],
            f"{scale}_h6_min_exact": got["h6_min"] == exp["min"],
            f"{scale}_h6_max_exact": got["h6_max"] == exp["max"],
            f"{scale}_h6_size6_exact": got["h6_size6"] == exp["size6"],
            f"{scale}_h6_gt10_exact": got["h6_gt10"] == exp["gt10"],
            f"{scale}_h6_ids_unique": got["h6_ids_unique"],
            f"{scale}_h6_all_ge6": got["h6_all_ge6"],
            f"{scale}_h6_capacity_feasible": got["h6_prior_capacity_feasible"],
            f"{scale}_donor_deferred": got["donor_deferred"],
        })

    failed = [name for name, value in checks.items() if not bool(value)]
    payload = {
        "phase": "F1-P_CONSTR-IMPL-02",
        "status": "PASS" if not failed else "FAIL",
        "freeze_gate": "PASS" if not failed else "FAIL",
        "implementation_commit": PARENT,
        "runbundle_zip_sha256": RUN_ZIP_SHA256,
        "rederived": {
            "reference_persons": REFERENCE_PERSONS,
            "full_h6_households_berlin": int(full_prior["full_scale_h6_prior"].sum()),
            "reconciled_fullscale_p6_persons": int(full_prior["person_target_6plus_full"].sum()),
            "published_1000A_1029_p6_persons": 242700,
            "scales": derived,
        },
        "formal_g1": cfg["project_gates"]["G1"],
        "formal_g2": cfg["project_gates"]["G2"],
        "checks": {name: bool(value) for name, value in checks.items()},
        "failed": failed,
        "next_step_if_pass": "COMMIT_IMPL02_A1_FREEZE",
    }
    print(json.dumps(payload, indent=2, sort_keys=True))
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
