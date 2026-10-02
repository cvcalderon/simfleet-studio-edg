from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path

import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[1]
PARENT = "48dddece478e30a5e592f4eda681e0b972df02db"
EXECUTION_COMMIT = "1530cac0b4d634eb064bc46d5fb7ee429518d208"
SELECTED = "DIST_REF_REFERENCE"
DA1 = "DIST_A_DA1"
MODEL_SHA = "21554c37d44aad7144c8daac1ddfd9e9a63402d59e105f9e790e83c1ea6e4cab"
MANIFEST_SHA = "4a30ae1f586418c31a55028e2902d28c43e234a1fddaadccba9103c1a09bd409"
CFG = ROOT / "configs/f3/f3_4f2c_distance_prior_main_freeze_v1.yaml"
SEL = ROOT / "configs/f3/f3_4f2c_selected_distance_prior_artifact_v1.json"
FILELIST = ROOT / "docs/F3_4F2C_OVERLAY_FILELIST_v1.txt"
CHECKSUMS = ROOT / "docs/F3_4F2C_OVERLAY_CHECKSUMS_v1.sha256"


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).rstrip("\n")


def status_scope() -> set[str]:
    output = git("status", "--short")
    return {line[3:] for line in output.splitlines() if line}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def verify_sha_manifest(base: Path, manifest_path: Path) -> bool:
    for line in manifest_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        expected, rel = line.split(maxsplit=1)
        path = base / rel.strip()
        if not path.is_file() or sha256(path) != expected:
            return False
    return True


def verify_bundle_checksums(run: Path) -> bool:
    manifest = run / "checksums.sha256"
    if not manifest.is_file():
        return False
    for line in manifest.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        expected, name = line.split(maxsplit=1)
        path = run / name.strip()
        if not path.is_file() or sha256(path) != expected:
            return False
    return True


def approx(value: object, expected: float, tol: float = 1e-6) -> bool:
    try:
        return abs(float(value) - expected) <= tol
    except (TypeError, ValueError):
        return False


def bool_value(value: object) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"true", "1", "yes"}


def empty_csv_payload(path: Path) -> bool:
    return path.is_file() and path.read_text(encoding="utf-8").strip() == ""


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", required=True)
    args = parser.parse_args()
    run = Path(args.run_dir).expanduser().resolve()

    cfg = yaml.safe_load(CFG.read_text(encoding="utf-8"))
    frozen = json.loads(SEL.read_text(encoding="utf-8"))
    manifest = json.loads((run / "run_manifest.json").read_text(encoding="utf-8"))
    proposed = json.loads(
        (run / "selected_component_artifact.json").read_text(encoding="utf-8")
    )
    primary = pd.read_csv(run / "primary_metrics.csv")
    summary = pd.read_csv(run / "isolated_summary_metrics.csv")
    guardrails = pd.read_csv(run / "isolated_guardrails.csv")
    grid = pd.read_csv(run / "grid_selection.csv")
    sensitivity = pd.read_csv(run / "sensitivity_metrics.csv")
    candidate_validation = pd.read_csv(run / "candidate_artifact_validation.csv")
    propagated = pd.read_csv(run / "propagated_runtime_guardrails.csv")
    validation = pd.read_csv(run / "validation.csv")
    issues = pd.read_csv(run / "issues.csv")

    primary_map = primary.set_index("artifact_id")["wasserstein_km_mean32"].to_dict()
    prop = propagated.set_index("artifact_id")
    candidate_validation_map = candidate_validation.set_index("artifact_id")
    da1_guard = guardrails.loc[
        guardrails["challenger_artifact_id"].eq(DA1)
    ].iloc[0]

    expected_scope = set(FILELIST.read_text(encoding="utf-8").splitlines())
    scope = status_scope()

    checks = {
        "head_exact_parent": git("rev-parse", "HEAD") == PARENT,
        "branch_main": git("branch", "--show-current") == "main",
        "ahead_zero": git("rev-list", "--count", "origin/main..HEAD") == "0",
        "behind_zero": git("rev-list", "--count", "HEAD..origin/main") == "0",
        "no_staged_changes": git("diff", "--cached", "--name-only") == "",
        "overlay_scope_exact": scope == expected_scope,
        "static_checksums_pass": verify_sha_manifest(ROOT, CHECKSUMS),
        "runbundle_checksums_pass": verify_bundle_checksums(run),
        "run_status_pass": manifest.get("status") == "PASS",
        "run_execution_commit_exact": (
            manifest.get("implementation_commit") == EXECUTION_COMMIT
        ),
        "cal_rows_2873": int(manifest.get("cal_rows_read_total_physical", -1)) == 2873,
        "isolated_rows_1147": int(manifest.get("cal_isolated_raw_rows", -1)) == 1147,
        "sensitivity_rows_1257": int(manifest.get("cal_sensitivity_rows", -1)) == 1257,
        "fixed_cohort_350": int(manifest.get("cal_fixed_source_cohort_days", -1)) == 350,
        "candidate_artifacts_5": int(manifest.get("candidate_artifacts", -1)) == 5,
        "proposal_exact": proposed.get("proposed_selected_artifact_id") == SELECTED,
        "proposal_base_exact": proposed.get("base_artifact_id") == SELECTED,
        "proposal_not_downstream_authorized": (
            proposed.get("authorized_for_downstream") is False
        ),
        "proposal_status_exact": (
            proposed.get("status")
            == "PROPOSED_BY_FROZEN_CAL_RULES_AWAITING_MAIN_FREEZE"
        ),
        "primary_reference_exact": approx(
            primary_map.get(SELECTED), 3.0134776044003124, 1e-12
        ),
        "primary_da1_exact": approx(primary_map.get(DA1), 2.5908176376904204, 1e-12),
        "da1_point_improvement_over_margin": (
            float(primary_map[SELECTED]) - float(primary_map[DA1]) >= 0.25
        ),
        "da1_guardrails_fail": not bool_value(da1_guard["guardrails_pass"]),
        "da1_p95_worsening_exact": approx(
            da1_guard["p95_abs_error_worsening_km"], 1.8529040985750047, 1e-12
        ),
        "da1_p95_exceeds_tolerance": (
            float(da1_guard["p95_abs_error_worsening_km"])
            > float(da1_guard["p95_tolerance_km"])
        ),
        "all_grid_unselected": (
            len(grid) == 4
            and not any(bool_value(v) for v in grid["selected_within_family"])
        ),
        "all_challenger_guardrails_fail": (
            len(guardrails) == 4
            and not any(bool_value(v) for v in guardrails["guardrails_pass"])
        ),
        "bootstrap_intentionally_empty": empty_csv_payload(
            run / "bootstrap_intervals.csv"
        ),
        "promotion_intentionally_empty": empty_csv_payload(
            run / "promotion_decisions.csv"
        ),
        "propagated_reference_zero": (
            SELECTED in prop.index
            and int(prop.loc[SELECTED, "runtime_invariant_violations"]) == 0
            and bool_value(prop.loc[SELECTED, "hard_pass"])
        ),
        "propagated_reference_rows_36449": (
            SELECTED in prop.index
            and int(prop.loc[SELECTED, "generated_distance_rows"]) == 36449
        ),
        "validation_all_pass": (
            len(validation) > 0 and validation["status"].eq("PASS").all()
        ),
        "issues_empty": len(issues) == 0,
        "freeze_artifact_exact": frozen.get("artifact_id") == SELECTED,
        "freeze_state_main_frozen": frozen.get("state") == "MAIN_FROZEN",
        "model_sha_exact": frozen.get("model_sha256") == MODEL_SHA,
        "manifest_sha_exact": frozen.get("manifest_sha256") == MANIFEST_SHA,
        "runbundle_selected_model_sha_exact": (
            SELECTED in candidate_validation_map.index
            and candidate_validation_map.loc[SELECTED, "model_sha256"] == MODEL_SHA
        ),
        "runbundle_selected_manifest_sha_exact": (
            SELECTED in candidate_validation_map.index
            and candidate_validation_map.loc[SELECTED, "manifest_sha256"]
            == MANIFEST_SHA
        ),
        "physical_model_sha_exact": sha256(
            ROOT
            / "artifacts/runs/F3_2g_distance_prior_fit_v1/models/DIST_REF/model.json"
        )
        == MODEL_SHA,
        "physical_manifest_sha_exact": sha256(
            ROOT
            / (
                "artifacts/runs/F3_2g_distance_prior_fit_v1/"
                "models/DIST_REF/artifact_manifest.json"
            )
        )
        == MANIFEST_SHA,
        "mean_report_only": summary["mean_role"].eq(
            "REPORT_ONLY_UNTHRESHOLDED"
        ).all(),
        "sensitivity_report_only": sensitivity["role"].eq("REPORT_ONLY").all(),
        "runtime_authorized": frozen.get("authorized_for_runtime_dgen") is True,
        "joint_not_authorized": (
            frozen.get("joint_cal_gate_authorized") is False
            and cfg["boundaries"]["joint_cal_gate_authorized"] is False
        ),
        "all_five_main_frozen": (
            cfg["boundaries"]["all_five_dgen_components_main_frozen"] is True
        ),
        "test_sealed": frozen.get("test_open_authorized") is False,
        "test_rows_zero": int(frozen.get("test_rows_read", -1)) == 0,
        "g2_not_evaluated": frozen.get("formal_g2") == "NOT_EVALUATED",
    }

    failed = [name for name, passed in checks.items() if not bool(passed)]
    payload = {
        "phase": "F3.4f-2c",
        "component": "DG_DISTANCE_PRIOR",
        "status": "PASS" if not failed else "FAIL",
        "main_freeze_gate": "PASS" if not failed else "FAIL",
        "selected_artifact_id": SELECTED,
        "selected_state_after_commit": "MAIN_FROZEN",
        "distance_prior_authorized_for_runtime_dgen": True,
        "all_five_dgen_components_main_frozen": True,
        "joint_cal_gate_authorized": False,
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
        "next_step_if_pass": (
            "COMMIT_DISTANCE_PRIOR_MAIN_FREEZE_THEN_BUILD_JOINT_CAL_PREOPEN"
        ),
    }
    print(json.dumps(payload, indent=2, sort_keys=True))
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
