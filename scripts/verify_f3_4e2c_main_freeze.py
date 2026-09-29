from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path

import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[1]
PARENT = "e7207c81b803444fdaae78bd3ec489a1021fb96f"
SELECTED = "TIME_B_TB2"
REFERENCE = "TIME_REF_REFERENCE"
MODEL_SHA = "74aa012647291854c4fa087f1dd798e9d909e3c681046f1447307a23a6d5f900"
MANIFEST_SHA = "ff3caa54e7ee11c2bde79e49da5604277d506c826b891fb7a1e4edd04b157c5a"
CFG = ROOT / "configs/f3/f3_4e2c_time_schedule_main_freeze_v1.yaml"
SEL = ROOT / "configs/f3/f3_4e2c_selected_time_schedule_artifact_v1.json"
FILELIST = ROOT / "docs/F3_4E2C_OVERLAY_FILELIST_v1.txt"
CHECKSUMS = ROOT / "docs/F3_4E2C_OVERLAY_CHECKSUMS_v1.sha256"


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).rstrip("\n")


def status_scope() -> set[str]:
    out = git("status", "--short")
    scope: set[str] = set()
    for line in out.splitlines():
        if not line:
            continue
        scope.add(line[3:])
    return scope


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def verify_sha_manifest(base: Path, manifest: Path) -> bool:
    for raw in manifest.read_text(encoding="utf-8").splitlines():
        raw = raw.strip()
        if not raw:
            continue
        expected, rel = raw.split(maxsplit=1)
        rel = rel.strip()
        if rel.startswith("*"):
            rel = rel[1:]
        p = base / rel
        if not p.is_file() or sha256(p) != expected:
            return False
    return True


def verify_bundle_checksums(run: Path) -> bool:
    manifest = run / "checksums.sha256"
    return manifest.is_file() and verify_sha_manifest(run, manifest)


def approx(value: object, expected: float, tol: float = 5e-6) -> bool:
    try:
        return abs(float(value) - expected) <= tol
    except (TypeError, ValueError):
        return False


def bool_value(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if pd.isna(value):
        return False
    return str(value).strip().lower() in {"true", "1", "yes"}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", required=True)
    args = parser.parse_args()
    run = Path(args.run_dir).expanduser().resolve()

    cfg = yaml.safe_load(CFG.read_text(encoding="utf-8"))
    frozen = json.loads(SEL.read_text(encoding="utf-8"))
    manifest = json.loads((run / "run_manifest.json").read_text(encoding="utf-8"))
    proposed = json.loads((run / "selected_component_artifact.json").read_text(encoding="utf-8"))
    primary = pd.read_csv(run / "primary_metrics.csv")
    grid = pd.read_csv(run / "grid_selection.csv")
    promotions = pd.read_csv(run / "promotion_decisions.csv")
    bootstrap = pd.read_csv(run / "bootstrap_intervals.csv")
    isolated = pd.read_csv(run / "isolated_temporal_guardrails.csv")
    propagated = pd.read_csv(run / "propagated_temporal_guardrails.csv")
    issues = pd.read_csv(run / "issues.csv")

    primary_map = primary.set_index("artifact_id")["value"].to_dict()
    tb2_grid = grid.loc[grid["artifact_id"].eq(SELECTED)]
    promo = promotions.iloc[0] if len(promotions) == 1 else None
    boot = bootstrap.iloc[0] if len(bootstrap) == 1 else None
    iso = isolated.set_index("artifact_id")
    prop = propagated.set_index("artifact_id")

    expected_scope = set(FILELIST.read_text(encoding="utf-8").splitlines())
    scope = status_scope()
    static_ok = verify_sha_manifest(ROOT, CHECKSUMS)

    checks = {
        "head_exact_parent": git("rev-parse", "HEAD") == PARENT,
        "branch_main": git("branch", "--show-current") == "main",
        "ahead_zero": git("rev-list", "--count", "origin/main..HEAD") == "0",
        "behind_zero": git("rev-list", "--count", "HEAD..origin/main") == "0",
        "no_staged_changes": git("diff", "--cached", "--name-only") == "",
        "overlay_scope_exact": scope == expected_scope,
        "static_checksums_pass": bool(static_ok),
        "runbundle_checksums_pass": verify_bundle_checksums(run),
        "run_status_pass": manifest.get("status") == "PASS",
        "run_commit_exact": manifest.get("implementation_commit") == PARENT,
        "cal_rows_1712": int(manifest.get("cal_rows_read_total_physical", -1)) == 1712,
        "isolated_rows_1243": int(manifest.get("cal_isolated_time_rows", -1)) == 1243,
        "fixed_cohort_378": int(manifest.get("cal_fixed_source_cohort_days", -1)) == 378,
        "candidate_artifacts_7": int(manifest.get("candidate_artifacts", -1)) == 7,
        "proposal_exact": proposed.get("proposed_selected_artifact_id") == SELECTED,
        "proposal_base_exact": proposed.get("base_artifact_id") == SELECTED,
        "proposal_not_downstream_authorized": proposed.get("authorized_for_downstream") is False,
        "proposal_status_exact": proposed.get("status") == "PROPOSED_BY_FROZEN_CAL_RULES_AWAITING_MAIN_FREEZE",
        "run_propagated_gate_pass": manifest.get("propagated_temporal_guardrail_pass") is True,
        "primary_rows_7": len(primary) == 7,
        "reference_primary_reported": approx(primary_map.get(REFERENCE), 0.252671),
        "tb2_primary_reported": approx(primary_map.get(SELECTED), 0.112080),
        "tb2_selected_within_family": len(tb2_grid) == 1 and bool_value(tb2_grid.iloc[0]["selected_within_family"]),
        "one_promotion": len(promotions) == 1,
        "promotion_ref_to_tb2": promo is not None and promo["incumbent_artifact_id"] == REFERENCE and promo["challenger_artifact_id"] == SELECTED and bool_value(promo["promoted"]),
        "promotion_margin_0005": promo is not None and approx(promo["practical_margin"], 0.005, 1e-12),
        "promotion_improvement_reported": promo is not None and approx(promo["point_improvement"], 0.140591),
        "bootstrap_one": len(bootstrap) == 1,
        "bootstrap_1000": boot is not None and int(boot["bootstrap_replicates"]) == 1000,
        "bootstrap_ci_lower_positive": boot is not None and float(boot["ci_lower"]) > 0,
        "bootstrap_ci_reported": boot is not None and approx(boot["ci_lower"], 0.084075) and approx(boot["ci_upper"], 0.163467),
        "isolated_reference_zero": REFERENCE in iso.index and int(iso.loc[REFERENCE, "temporal_invariant_violations"]) == 0 and bool_value(iso.loc[REFERENCE, "hard_pass"]),
        "isolated_tb2_zero": SELECTED in iso.index and int(iso.loc[SELECTED, "temporal_invariant_violations"]) == 0 and bool_value(iso.loc[SELECTED, "hard_pass"]),
        "propagated_reference_zero": REFERENCE in prop.index and int(prop.loc[REFERENCE, "temporal_invariant_violations"]) == 0 and bool_value(prop.loc[REFERENCE, "hard_pass"]),
        "propagated_tb2_zero": SELECTED in prop.index and int(prop.loc[SELECTED, "temporal_invariant_violations"]) == 0 and bool_value(prop.loc[SELECTED, "hard_pass"]),
        "propagated_rows_reference_39449": REFERENCE in prop.index and int(prop.loc[REFERENCE, "generated_time_rows"]) == 39449,
        "propagated_rows_tb2_39449": SELECTED in prop.index and int(prop.loc[SELECTED, "generated_time_rows"]) == 39449,
        "issues_empty": len(issues) == 0,
        "freeze_artifact_exact": frozen.get("artifact_id") == SELECTED,
        "freeze_state_main_frozen": frozen.get("state") == "MAIN_FROZEN",
        "model_sha_exact": frozen.get("model_sha256") == MODEL_SHA,
        "manifest_sha_exact": frozen.get("manifest_sha256") == MANIFEST_SHA,
        "runtime_authorized": frozen.get("authorized_for_runtime_dgen") is True,
        "next_component_not_authorized": frozen.get("next_component_authorized") is False,
        "distance_prior_not_authorized": frozen.get("distance_prior_real_cal_authorized") is False and cfg["boundaries"]["distance_prior_real_cal_authorized"] is False,
        "test_sealed": frozen.get("test_open_authorized") is False,
        "g2_not_evaluated": frozen.get("formal_g2") == "NOT_EVALUATED",
        "time_b_full_chain_policy_frozen": cfg["sampling_policy"]["propagated_time_b"] == "EXACT_TIME_B_FULL_CHAIN_MIN_SLACK_CONDITIONAL_V1",
        "reference_full_chain_policy_frozen": cfg["sampling_policy"]["propagated_time_ref"] == "EXACT_REFERENCE_FULL_CHAIN_SUPPORT_CONDITIONAL_V1",
    }

    failed = [k for k, v in checks.items() if not bool(v)]
    payload = {
        "phase": "F3.4e-2c",
        "component": "DG_TIME_SCHEDULE",
        "status": "PASS" if not failed else "FAIL",
        "main_freeze_gate": "PASS" if not failed else "FAIL",
        "selected_artifact_id": SELECTED,
        "selected_state_after_commit": "MAIN_FROZEN",
        "time_schedule_authorized_for_runtime_dgen": True,
        "distance_prior_real_cal_authorized": False,
        "test_open_authorized": False,
        "formal_g2": "NOT_EVALUATED",
        "checks": {k: bool(v) for k, v in checks.items()},
        "failed": failed,
        "overlay_scope": {
            "expected_count": len(expected_scope),
            "actual_count": len(scope),
            "missing": sorted(expected_scope - scope),
            "unexpected": sorted(scope - expected_scope),
        },
        "next_step_if_pass": "COMMIT_TIME_SCHEDULE_MAIN_FREEZE_THEN_BUILD_CLOSURE",
    }
    print(json.dumps(payload, indent=2, sort_keys=True))
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
