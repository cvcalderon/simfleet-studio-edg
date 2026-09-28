from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path

import pandas as pd
import yaml

ROOT = Path.cwd()
PARENT = "6c2c27cd92a835a641a044c9e758f7c0cf1e1742"
SELECTED = "DG_ACTIVITY_CHAIN::CHAIN_A::CHA2"
MODEL_SHA = "242085ebab9eb5ec8a53ea3b8ffe65c1d1e1fdb660bcacff0ab172d1b5ef1ecf"
MANIFEST_SHA = "337140dd45522a47659603998838a3c869646cbd70961ba874d6f34be555ea73"
PURPOSE_SHA = "ab42cf42c9568ef4f085f071299fc941d421c42337f353e00870cd05c94f94fb"

CFG = ROOT / "configs/f3/f3_4d2c_activity_chain_main_freeze_v1.yaml"
SELECTED_JSON = ROOT / "configs/f3/f3_4d2c_selected_activity_chain_artifact_v1.json"
FILELIST = ROOT / "docs/F3_4D2C_OVERLAY_FILELIST_v1.txt"
CHECKSUMS = ROOT / "docs/F3_4D2C_OVERLAY_CHECKSUMS_v1.sha256"


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], text=True).rstrip("\n")


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def approx(a: float, b: float, tol: float = 1e-12) -> bool:
    return abs(float(a) - float(b)) <= tol


def verify_bundle_checksums(run: Path) -> bool:
    manifest = run / "checksums.sha256"
    if not manifest.is_file():
        return False
    for line in manifest.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        digest, rel = line.split(maxsplit=1)
        if sha256(run / rel.strip()) != digest:
            return False
    return True


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", type=Path, required=True)
    args = parser.parse_args()
    run = args.run_dir.expanduser().resolve()

    cfg = yaml.safe_load(CFG.read_text(encoding="utf-8"))
    frozen = json.loads(SELECTED_JSON.read_text(encoding="utf-8"))
    manifest = json.loads((run / "run_manifest.json").read_text(encoding="utf-8"))
    proposed = json.loads(
        (run / "selected_component_artifact.json").read_text(encoding="utf-8")
    )
    primary = pd.read_csv(run / "primary_metrics.csv")
    grid = pd.read_csv(run / "grid_selection.csv")
    promotions = pd.read_csv(run / "promotion_decisions.csv")
    bootstrap = pd.read_csv(run / "bootstrap_intervals.csv")
    isolated = pd.read_csv(run / "isolated_guardrails.csv")
    propagated = pd.read_csv(run / "propagated_guardrails.csv")
    issues = pd.read_csv(run / "issues.csv")

    scope = {
        line[3:]
        for line in git("status", "--porcelain").splitlines()
        if line
    }
    expected_scope = {
        line.strip()
        for line in FILELIST.read_text(encoding="utf-8").splitlines()
        if line.strip()
    }

    static_ok = True
    for line in CHECKSUMS.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        digest, rel = line.split(maxsplit=1)
        static_ok &= sha256(ROOT / rel.strip()) == digest

    primary_map = dict(zip(primary["artifact_id"], primary["value"], strict=True))

    cha2_grid = grid[grid["artifact_id"].eq(SELECTED)]
    b_rows = grid[grid["candidate_id"].eq("CHAIN_B")]

    promo = promotions.iloc[0] if len(promotions) == 1 else None
    boot = bootstrap.iloc[0] if len(bootstrap) == 1 else None
    iso = isolated[
        isolated["challenger_artifact_id"].eq(SELECTED)
        & isolated["incumbent_artifact_id"].eq(
            "DG_ACTIVITY_CHAIN::CHAIN_REF::REFERENCE"
        )
    ]
    prop = propagated[
        propagated["challenger_artifact_id"].eq(SELECTED)
        & propagated["incumbent_artifact_id"].eq(
            "DG_ACTIVITY_CHAIN::CHAIN_REF::REFERENCE"
        )
    ]

    checks = {
        "head_exact_parent": git("rev-parse", "HEAD") == PARENT,
        "branch_main": git("branch", "--show-current") == "main",
        "ahead_zero": git("rev-list", "--count", "origin/main..HEAD") == "0",
        "behind_zero": git("rev-list", "--count", "HEAD..origin/main") == "0",
        "no_staged_changes": git("diff", "--cached", "--name-only") == "",
        "overlay_scope_exact": scope == expected_scope,
        "static_checksums_pass": bool(static_ok),
        "runbundle_checksums_pass": verify_bundle_checksums(run),
        "run_status_pass": manifest["status"] == "PASS",
        "run_commit_exact": manifest["implementation_commit"]
        == "16756fd766aaedea8ad0e532e135899d4b13ebfb",
        "cal_rows_1853": int(manifest["cal_rows_read_total_physical"]) == 1853,
        "isolated_rows_1065": int(manifest["cal_isolated_transition_rows"]) == 1065,
        "fixed_cohort_319": int(manifest["cal_fixed_source_cohort_days"]) == 319,
        "candidate_artifacts_6": int(manifest["candidate_artifacts"]) == 6,
        "proposal_exact": proposed["proposed_selected_artifact_id"] == SELECTED,
        "proposal_not_downstream_authorized": proposed["authorized_for_downstream"]
        is False,
        "primary_rows_6": len(primary) == 6,
        "reference_primary_exact": approx(
            primary_map["DG_ACTIVITY_CHAIN::CHAIN_REF::REFERENCE"],
            3.042920920013547,
        ),
        "cha2_primary_exact": approx(primary_map[SELECTED], 1.3549031390197808),
        "cha2_selected_within_family": len(cha2_grid) == 1
        and bool(cha2_grid.iloc[0]["selected_within_family"]),
        "all_chain_b_guardrails_fail": len(b_rows) == 3
        and not b_rows["guardrails_pass"].astype(bool).any(),
        "one_promotion": len(promotions) == 1,
        "promotion_ref_to_cha2": promo is not None
        and promo["incumbent_artifact_id"]
        == "DG_ACTIVITY_CHAIN::CHAIN_REF::REFERENCE"
        and promo["challenger_artifact_id"] == SELECTED
        and bool(promo["promoted"]),
        "promotion_improvement_exact": promo is not None
        and approx(promo["point_improvement"], 1.6880177809937664),
        "promotion_margin_001": promo is not None
        and approx(promo["practical_margin"], 0.01),
        "bootstrap_one": len(bootstrap) == 1,
        "bootstrap_ci_lower_positive": boot is not None
        and float(boot["ci_lower"]) > 0,
        "bootstrap_ci_exact": boot is not None
        and approx(boot["ci_lower"], 0.24699909115857205)
        and approx(boot["ci_upper"], 3.7193672069888444),
        "isolated_guardrails_pass": len(iso) == 1
        and bool(iso.iloc[0]["guardrails_pass"]),
        "propagated_guardrails_pass": len(prop) == 1
        and bool(prop.iloc[0]["guardrails_pass"]),
        "issues_empty": len(issues) == 0,
        "freeze_artifact_exact": frozen["artifact_id"] == SELECTED,
        "freeze_state_main_frozen": frozen["state"] == "MAIN_FROZEN",
        "model_sha_exact": frozen["model_sha256"] == MODEL_SHA,
        "manifest_sha_exact": frozen["manifest_sha256"] == MANIFEST_SHA,
        "purpose_sha_exact": frozen["purpose_artifact_sha256"] == PURPOSE_SHA,
        "runtime_authorized": frozen["authorized_for_runtime_dgen"] is True,
        "next_component_not_authorized": frozen["next_component_authorized"] is False,
        "time_schedule_real_cal_not_authorized": cfg["boundaries"][
            "real_time_schedule_cal_open_authorized"
        ]
        is False,
        "test_sealed": frozen["test_open_authorized"] is False,
        "g2_not_evaluated": frozen["formal_g2"] == "NOT_EVALUATED",
    }

    failed = [key for key, value in checks.items() if not value]
    payload = {
        "phase": "F3.4d-2c",
        "component": "DG_ACTIVITY_CHAIN",
        "status": "PASS" if not failed else "FAIL",
        "main_freeze_gate": "PASS" if not failed else "FAIL",
        "selected_artifact_id": SELECTED,
        "selected_state_after_commit": "MAIN_FROZEN",
        "activity_chain_authorized_for_runtime_dgen": True,
        "next_component_authorized": False,
        "real_time_schedule_cal_open_authorized": False,
        "test_open_authorized": False,
        "formal_g2": "NOT_EVALUATED",
        "checks": checks,
        "failed": failed,
        "overlay_scope": {
            "expected_count": len(expected_scope),
            "actual_count": len(scope),
            "missing": sorted(expected_scope - scope),
            "unexpected": sorted(scope - expected_scope),
        },
    }
    print(json.dumps(payload, indent=2, sort_keys=True))
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
