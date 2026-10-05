"""Commit-bound M realization runner for F1-P_CONSTR G1 HOLD-MREAL-001."""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

SELECTED = "P_CONSTR_RMIN_V2_HD_U"
SCALE = "M"
SCHEMA = "simfleet-edg-f1-pconstr-g1-hold-mreal01-runbundle-v1"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _git(root: Path, *args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=root, text=True).strip()


def validate_execution_authorization(auth_path: Path, repo_root: Path) -> dict[str, Any]:
    auth = json.loads(auth_path.read_text(encoding="utf-8"))
    cfg = yaml.safe_load(
        (repo_root / "configs/f1/f1_pconstr_g1_hold_mreal01_preopen_v1.yaml").read_text(
            encoding="utf-8"
        )
    )
    head = _git(repo_root, "rev-parse", "HEAD")
    origin = _git(repo_root, "rev-parse", "origin/main")
    branch = _git(repo_root, "branch", "--show-current")
    worktree = _git(repo_root, "status", "--porcelain")
    checks = {
        "schema": auth.get("schema_version")
        == "simfleet-edg-f1-pconstr-g1-hold-mreal01-execution-authorization-v1",
        "phase": auth.get("phase") == "F1-P_CONSTR-G1-HOLD-MREAL-001",
        "authorized": auth.get("authorized") is True,
        "status": auth.get("authorization_status") == "AUTHORIZED_A1",
        "mreal_open": auth.get("mreal_execution_authorized") is True,
        "branch_main": branch == "main",
        "head_origin_equal": head == origin,
        "worktree_clean": worktree == "",
        "runner_commit_exact": auth.get("authorized_runner_commit") == head,
        "required_preopen_commit_exact": auth.get("required_preopen_commit") == head,
        "candidate_exact": auth.get("selected_candidate") == SELECTED,
        "scale_exact": auth.get("scale_id") == SCALE,
        "candidate_seed_exact": auth.get("candidate_master_seed") == 20261005,
        "h6_seed_exact": auth.get("h6_master_seed") == 20261004,
        "holdout_io_closed": auth.get("holdout_value_io_authorized") is False,
        "holdout_eval_closed": auth.get("holdout_metric_evaluation_authorized") is False,
        "cal_closed": auth.get("cal_reopen") is False,
        "test_closed": auth.get("mid_test_reopen") is False,
        "plr_closed": auth.get("plr_allocation") is False,
        "f3_closed": auth.get("f3_modified") is False,
        "config_candidate_exact": cfg["execution_realization"]["selected_candidate"] == SELECTED,
        "config_scale_exact": cfg["execution_realization"]["scale_id"] == SCALE,
        "holdout_still_unread": cfg["boundaries"]["holdout_1000A_1035_values_read"] is False,
        "holdout_still_unacquired": cfg["boundaries"]["holdout_1000A_1035_acquired"] is False,
    }
    failed = [name for name, ok in checks.items() if not ok]
    if failed:
        raise PermissionError(f"MREAL execution authorization rejected: {failed}")
    return {"authorized": True, "repository_head": head, "checks": checks}


def _write_csv(df: pd.DataFrame, path: Path) -> None:
    df.to_csv(path, index=False, lineterminator="\n")


def run_mreal(repo_root: Path, auth_path: Path, output_dir: Path) -> dict[str, Any]:
    # Authorization MUST precede output staging and every population-source read.
    auth_state = validate_execution_authorization(auth_path, repo_root)
    if output_dir.exists() or output_dir.with_name(output_dir.name + ".partial").exists():
        raise FileExistsError("MREAL output or .partial already exists; refusing overwrite")

    partial = output_dir.with_name(output_dir.name + ".partial")
    partial.mkdir(parents=True, exist_ok=False)
    try:
        from simfleet_edg.common.population_materializer import load_activity_recoding
        from simfleet_edg.population.candidate_materialization import (
            build_pconstr_selection,
            build_six_plus_blueprint,
            materialize_variant,
            validate_variant,
        )
        from simfleet_edg.population.equivalence import fit_equivalence_plan
        from simfleet_edg.repro.f1_pconstr_impl03_candidates import (
            build_upstream_scale,
            load_catalog_from_config,
        )

        cfg = yaml.safe_load(
            (repo_root / "configs/f1/f1_pconstr_g1_hold_mreal01_preopen_v1.yaml").read_text(
                encoding="utf-8"
            )
        )
        impl03_path = repo_root / cfg["frozen_upstream"]["impl03_candidate_config"]
        impl03 = yaml.safe_load(impl03_path.read_text(encoding="utf-8"))

        projected, h6_households = build_upstream_scale(repo_root, impl03, SCALE)
        catalog = load_catalog_from_config(repo_root, impl03)
        plan, class_fit, fit_audit = fit_equivalence_plan(
            projected, catalog.equivalence_catalog
        )
        selection = build_pconstr_selection(
            plan, catalog, scale_id=SCALE, variant_id=SELECTED
        )
        h6_hh_blueprint, h6_person_blueprint = build_six_plus_blueprint(
            projected, h6_households, catalog, scale_id=SCALE
        )
        activity = load_activity_recoding(
            repo_root / impl03["sources"]["activity_recoding"]["path"]
        )
        households, persons, resources = materialize_variant(
            selection,
            h6_hh_blueprint,
            h6_person_blueprint,
            catalog,
            activity,
            variant_id=SELECTED,
            scale_id=SCALE,
        )
        audit = validate_variant(
            SELECTED, SCALE, projected, households, persons, resources, catalog
        )

        observed = audit.__dict__.copy()
        strict_persons = int(
            persons.loc[
                persons["household_id"].isin(
                    set(
                        households.loc[
                            households["household_size_code"] != "PERSON06UM",
                            "household_id",
                        ]
                    )
                )
            ].shape[0]
        )
        six_plus_persons = int(len(persons) - strict_persons)
        observed.update(
            {
                "strict_persons": strict_persons,
                "six_plus_persons": six_plus_persons,
                "h6_min_size": int(
                    households.loc[
                        households["household_size_code"] == "PERSON06UM",
                        "materialized_member_count",
                    ].min()
                ),
                "h6_max_size": int(
                    households.loc[
                        households["household_size_code"] == "PERSON06UM",
                        "materialized_member_count",
                    ].max()
                ),
            }
        )
        expected = dict(cfg["expected_M_materialization"])
        anchor_keys = list(expected)
        anchor_ok = all(observed[k] == expected[k] for k in anchor_keys)
        if not anchor_ok:
            raise AssertionError(
                f"M realization anchors differ from frozen expectation: "
                f"expected={expected} observed={{k: observed[k] for k in anchor_keys}}"
            )

        # Strong structural invariants independent of the holdout.
        member_counts = persons.groupby("household_id").size()
        expected_counts = households.set_index("household_id")[
            "materialized_member_count"
        ].astype(int)
        member_counts = member_counts.reindex(expected_counts.index, fill_value=0).astype(int)
        validations = {
            "anchors_exact": anchor_ok,
            "household_ids_unique": bool(households["household_id"].is_unique),
            "person_ids_unique": bool(persons["person_id"].is_unique),
            "no_orphan_persons": bool(
                persons["household_id"].isin(set(households["household_id"])).all()
            ),
            "member_counts_exact": bool(member_counts.equals(expected_counts)),
            "train_only_household_donors": bool(households["donor_split"].eq("TRAIN").all()),
            "scale_exact": bool(households["scale_id"].eq(SCALE).all())
            and bool(persons["scale_id"].eq(SCALE).all()),
            "variant_exact": bool(households["population_variant_id"].eq(SELECTED).all())
            and bool(persons["population_variant_id"].eq(SELECTED).all()),
            "plr_not_allocated": bool(households["home_zone_level"].eq("BEZIRK").all()),
            "holdout_not_evaluated": True,
        }
        failed = [k for k, v in validations.items() if not v]
        if failed:
            raise AssertionError(f"M realization validation failed: {failed}")

        files = {
            "households": partial / f"M_{SELECTED}_households.csv",
            "persons": partial / f"M_{SELECTED}_persons.csv",
            "resources": partial / f"M_{SELECTED}_resources.csv",
            "projected_cube_M": partial / "projected_cube_M.csv",
            "h6_households_M": partial / "h6_households_M.csv",
            "equivalence_plan_M": partial / "equivalence_plan_M.csv",
            "equivalence_class_fit_M": partial / "equivalence_class_fit_M.csv",
        }
        _write_csv(households, files["households"])
        _write_csv(persons, files["persons"])
        _write_csv(resources, files["resources"])
        _write_csv(projected, files["projected_cube_M"])
        _write_csv(h6_households, files["h6_households_M"])
        _write_csv(plan, files["equivalence_plan_M"])
        _write_csv(class_fit, files["equivalence_class_fit_M"])
        _write_csv(pd.DataFrame([observed]), partial / "candidate_summary_M.csv")
        _write_csv(
            pd.DataFrame(
                [{"check": k, "status": "PASS" if v else "FAIL"} for k, v in validations.items()]
            ),
            partial / "validation.csv",
        )
        core_hashes = {name: sha256_file(path) for name, path in files.items()}
        (partial / "core_hashes.json").write_text(
            json.dumps(core_hashes, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        manifest = {
            "schema_version": SCHEMA,
            "phase": "F1-P_CONSTR-G1-HOLD-MREAL-001",
            "status": "PASS",
            "git_commit": auth_state["repository_head"],
            "selected_candidate": SELECTED,
            "scale_id": SCALE,
            "candidate_master_seed": 20261005,
            "h6_master_seed": 20261004,
            "candidate_summary": observed,
            "equivalence_fit": fit_audit.__dict__,
            "core_hashes": core_hashes,
            "holdout_1000A_1035_acquired": False,
            "holdout_1000A_1035_values_read": False,
            "holdout_metric_evaluation": False,
            "cal_reopened": False,
            "mid_test_reopened": False,
            "spatial_plr_allocation": False,
            "f3_modified": False,
            "G1": "OPEN",
            "G2": "PASS_CLOSED_DO_NOT_REOPEN",
            "hold_thresh_001": "OPEN",
            "hold_mreal_001": "PROPOSED_RESOLVED_AWAITING_MAIN_FREEZE",
        }
        (partial / "run_manifest.json").write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        with (partial / "checksums.sha256").open("w", encoding="utf-8") as f:
            for path in sorted(partial.iterdir(), key=lambda p: p.name):
                if path.is_file() and path.name != "checksums.sha256":
                    f.write(f"{sha256_file(path)}  {path.name}\n")
        partial.rename(output_dir)
        return manifest
    except Exception:
        # Keep .partial evidence on failure. Never silently delete it.
        raise


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", required=True)
    parser.add_argument("--authorization-json", required=True)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()
    result = run_mreal(
        Path(args.repo_root).expanduser().resolve(),
        Path(args.authorization_json).expanduser().resolve(),
        Path(args.output_dir).expanduser().resolve(),
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
