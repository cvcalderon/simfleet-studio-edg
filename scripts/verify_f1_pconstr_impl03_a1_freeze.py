#!/usr/bin/env python3
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
CFG = ROOT / "configs/f1/f1_pconstr_impl03_a1_freeze_v1.yaml"
AUDIT = ROOT / "docs/F1_PCONSTR_IMPL03_A1_MAIN_AUDIT_v1.json"
CANDIDATE_SNAPSHOT = ROOT / "docs/F1_PCONSTR_IMPL03_CANDIDATE_SUMMARY_S_A1_SNAPSHOT_v1.csv"
M_SNAPSHOT = ROOT / "docs/F1_PCONSTR_IMPL03_M_PLAN_SUMMARY_A1_SNAPSHOT_v1.csv"
VALIDATION_SNAPSHOT = ROOT / "docs/F1_PCONSTR_IMPL03_VALIDATION_A1_SNAPSHOT_v1.csv"
H6_SNAPSHOT = ROOT / "docs/F1_PCONSTR_IMPL03_SIX_PLUS_HASHES_A1_SNAPSHOT_v1.csv"
CATALOG_SNAPSHOT = ROOT / "docs/F1_PCONSTR_IMPL03_CATALOG_SUMMARY_A1_SNAPSHOT_v1.csv"
FILELIST = ROOT / "docs/F1_PCONSTR_IMPL03_FREEZE_OVERLAY_FILELIST_v1.txt"
PARENT = "9feb3471b8c1581b18571cbdc0b9e27001e3f632"
RUN_ZIP_SHA256 = "78c2a939cd7de08b048aed0cbd2a21abed73c87b68ce71860af1bbe321dd42a6"
VARIANTS = ("P_TRS_V1_FINAL", "P_CONSTR_RMIN_V2_HD_U", "P_CONSTR_RMIN_V2_HD_W")
KEY = ["bezirk_code", "age_zensus_11_source_code", "sex_code", "household_size_code"]


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def verify_checksum_manifest(directory: Path) -> bool:
    manifest = directory / "checksums.sha256"
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


def normalized_h6_blueprint(run: Path, variant: str) -> pd.DataFrame:
    hh = pd.read_csv(run / f"S_{variant}_households.csv", dtype=str)
    pp = pd.read_csv(run / f"S_{variant}_persons.csv", dtype=str)
    hh["draw_index_i"] = pd.to_numeric(hh["draw_index"]).astype(int)
    hh["materialized_member_count_i"] = pd.to_numeric(hh["materialized_member_count"]).astype(int)
    h6 = hh.loc[hh["household_size_code"].eq("PERSON06UM")].copy()
    h6 = h6.sort_values(["bezirk_code", "draw_index_i", "household_id"]).reset_index(drop=True)
    h6["local_h6_ordinal"] = h6.groupby("bezirk_code").cumcount() + 1
    meta = h6[["household_id", "bezirk_code", "local_h6_ordinal", "source_household_id", "materialized_member_count_i"]]
    p = pp.loc[pp["household_id"].isin(set(meta["household_id"]))].copy()
    p = p.merge(meta, on=["household_id", "bezirk_code"], how="left", suffixes=("_person", "_hh"))
    p = p.sort_values(["household_id", "person_id"]).reset_index(drop=True)
    p["slot"] = p.groupby("household_id").cumcount() + 1
    return p[[
        "bezirk_code", "local_h6_ordinal", "source_household_id_hh",
        "materialized_member_count_i", "slot", "source_person_id",
        "age_zensus_11_source_code", "sex_code", "age_years",
        "primary_activity_status",
    ]].reset_index(drop=True)


def derive_variant(run: Path, variant: str, projected: pd.DataFrame) -> dict:
    hh = pd.read_csv(run / f"S_{variant}_households.csv", dtype={"bezirk_code": str})
    pp = pd.read_csv(run / f"S_{variant}_persons.csv", dtype={"bezirk_code": str})
    rr = pd.read_csv(run / f"S_{variant}_resources.csv")
    counts = pp.groupby("household_id").size()
    expected_counts = hh.set_index("household_id")["materialized_member_count"].astype(int)
    counts = counts.reindex(expected_counts.index, fill_value=0).astype(int)
    pp2 = pp.merge(hh[["household_id", "household_size_code"]], on="household_id", how="left")
    gen = pp2.groupby(KEY).size().rename("generated_persons").reset_index()
    comp = projected.merge(gen, on=KEY, how="outer").fillna({"projected_persons": 0, "generated_persons": 0})
    comp["absolute_error"] = (comp["generated_persons"] - comp["projected_persons"]).abs().astype(int)
    return {
        "households": len(hh),
        "persons": len(pp),
        "resources": len(rr),
        "member_mismatches": int((counts != expected_counts).sum()),
        "household_ids_unique": bool(hh["household_id"].is_unique),
        "person_ids_unique": bool(pp["person_id"].is_unique),
        "resource_ids_unique": bool(rr["relation_id"].is_unique),
        "person_fk_missing": int((~pp["household_id"].isin(hh["household_id"])).sum()),
        "resource_hh_fk_missing": int((~rr["household_id"].isin(hh["household_id"])).sum()),
        "donor_splits": sorted(hh["donor_split"].astype(str).unique().tolist()),
        "six_plus_households": int(hh["household_size_code"].eq("PERSON06UM").sum()),
        "target_fit_l1": int(comp["absolute_error"].sum()),
        "target_fit_max_abs": int(comp["absolute_error"].max()),
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
    validation = pd.read_csv(run / "validation.csv")
    candidate = pd.read_csv(run / "candidate_summary_S.csv")
    m_summary = pd.read_csv(run / "M_plan_summary.csv")
    h6_hashes = pd.read_csv(run / "six_plus_branch_hashes.csv")
    catalog = pd.read_csv(run / "catalog_summary.csv")
    performance = pd.read_csv(run / "performance.csv")
    projected = pd.read_csv(run / "projected_cube_S.csv", dtype={"bezirk_code": str})[KEY + ["projected_persons"]]
    expected_scope = set(FILELIST.read_text(encoding="utf-8").splitlines())
    actual_scope = {line[3:] for line in git("status", "--short").splitlines() if line}

    derived = {v: derive_variant(run, v, projected) for v in VARIANTS}
    blueprints = {v: normalized_h6_blueprint(run, v) for v in VARIANTS}
    h6_equal = blueprints[VARIANTS[0]].equals(blueprints[VARIANTS[1]]) and blueprints[VARIANTS[0]].equals(blueprints[VARIANTS[2]])

    plan_m = pd.read_csv(run / "equivalence_plan_M.csv", dtype={"bezirk_code": str})
    fit_m = pd.read_csv(run / "equivalence_class_fit_M.csv", dtype={"bezirk_code": str})
    m_derived = {
        "groups": int(plan_m[["bezirk_code", "household_size_code"]].drop_duplicates().shape[0]),
        "generated_households": int(plan_m["n_households"].sum()),
        "target_persons": int(fit_m["target_persons"].sum()),
        "generated_persons": int(fit_m["generated_persons"].sum()),
        "l1_person_cell_error": int(fit_m["absolute_error"].sum()),
        "max_abs_person_cell_error": int(fit_m["absolute_error"].max()),
        "positive_equivalence_classes": int(plan_m.loc[plan_m["n_households"].gt(0), "equivalence_class_id"].nunique()),
        "plan_rows": int(len(plan_m)),
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
        "run_checksums_pass": verify_checksum_manifest(run),
        "manifest_schema_exact": manifest["schema_version"] == "simfleet-edg-f1-pconstr-impl03-runbundle-v1",
        "manifest_phase_exact": manifest["phase_id"] == "F1-P_CONSTR-IMPL-03",
        "manifest_status_pass": manifest["status"] == "PASS",
        "execution_commit_exact": manifest["git"]["commit"] == PARENT,
        "execution_origin_exact": manifest["git"]["origin_main"] == PARENT,
        "execution_branch_main": manifest["git"]["branch"] == "main",
        "execution_worktree_clean": bool(manifest["git"]["worktree_clean_before_run"]),
        "candidate_snapshot_exact": candidate.equals(pd.read_csv(CANDIDATE_SNAPSHOT)),
        "M_snapshot_exact": m_summary.equals(pd.read_csv(M_SNAPSHOT)),
        "validation_snapshot_exact": validation.equals(pd.read_csv(VALIDATION_SNAPSHOT)),
        "h6_hash_snapshot_exact": h6_hashes.equals(pd.read_csv(H6_SNAPSHOT)),
        "catalog_snapshot_exact": catalog.equals(pd.read_csv(CATALOG_SNAPSHOT)),
        "validation_33_all_pass": len(validation) == 33 and bool(validation["status"].eq("PASS").all()),
        "performance_positive": bool((performance["wall_seconds"] > 0).all()),
        "common_h6_blueprint_rederived": bool(h6_equal),
        "h6_hashes_common": h6_hashes["signature_sha256"].nunique() == 1 and int(h6_hashes["person_rows"].min()) == 685 and int(h6_hashes["person_rows"].max()) == 685,
        "M_plan_rederived_exact": m_derived == {k: cfg["M_plan_anchors"][k] for k in m_derived},
        "calibration_not_read": manifest["policy"]["calibration_read"] is False,
        "mid_test_not_read_by_impl03": manifest["policy"]["mid_test_read_by_impl03"] is False,
        "holdout_not_read": manifest["policy"]["holdout_1000A_1035_read"] is False,
        "candidate_selection_deferred": manifest["policy"]["candidate_selection"] is False,
        "g1_threshold_not_tuned": manifest["policy"]["g1_threshold_tuning"] is False,
        "plr_not_allocated": manifest["policy"]["spatial_plr_allocation"] is False,
        "f3_not_modified": manifest["policy"]["f3_modified"] is False,
        "g1_open": manifest["policy"]["G1"] == "OPEN",
        "g2_closed": manifest["policy"]["G2"] == "PASS_CLOSED_DO_NOT_REOPEN",
    }

    expected_s = cfg["S_anchors"]
    for v in VARIANTS:
        got = derived[v]
        exp = expected_s[v]
        checks.update({
            f"{v}_households_exact": got["households"] == int(exp["households"]),
            f"{v}_persons_exact": got["persons"] == int(exp["persons"]),
            f"{v}_resources_exact": got["resources"] == int(exp["resources"]),
            f"{v}_fit_l1_exact": got["target_fit_l1"] == int(exp["target_fit_l1"]),
            f"{v}_fit_max_exact": got["target_fit_max_abs"] == int(exp["target_fit_max_abs"]),
            f"{v}_member_counts_exact": got["member_mismatches"] == 0,
            f"{v}_ids_unique": got["household_ids_unique"] and got["person_ids_unique"] and got["resource_ids_unique"],
            f"{v}_fk_valid": got["person_fk_missing"] == 0 and got["resource_hh_fk_missing"] == 0,
            f"{v}_train_only": got["donor_splits"] == ["TRAIN"],
            f"{v}_six_plus_exact": got["six_plus_households"] == 80,
        })

    failed = [name for name, ok in checks.items() if not bool(ok)]
    payload = {
        "phase": "F1-P_CONSTR-IMPL-03",
        "status": "PASS" if not failed else "FAIL",
        "freeze_gate": "PASS" if not failed else "FAIL",
        "implementation_commit": PARENT,
        "runbundle_zip_sha256": RUN_ZIP_SHA256,
        "derived_S": derived,
        "derived_M_plan": m_derived,
        "boundaries": cfg["boundaries"],
        "formal_g1": cfg["project_gates"]["G1"],
        "formal_g2": cfg["project_gates"]["G2"],
        "checks": {k: bool(v) for k, v in checks.items()},
        "failed": failed,
        "next_step_if_pass": "COMMIT_IMPL03_A1_FREEZE",
    }
    print(json.dumps(payload, indent=2, sort_keys=True))
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
