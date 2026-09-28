from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

import yaml

ROOT = Path.cwd()
PARENT = "a652d361f7fb938401ef41cae5b126fad6208cee"
CFG = ROOT / "configs/f3/f3_4d2br1_activity_chain_precal_remediation_v1.yaml"
ARTIFACT = ROOT / "configs/f3/f3_4d2br1_purpose_attribution_artifact_v1.json"
WITNESS = ROOT / "docs/F3_4D2BR1_TRAIN_PURPOSE_WITNESS_v1.json"
FILELIST = ROOT / "docs/F3_4D2BR1_OVERLAY_FILELIST_v1.txt"


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


def main() -> None:
    cfg = yaml.safe_load(CFG.read_text(encoding="utf-8"))
    artifact = json.loads(ARTIFACT.read_text(encoding="utf-8"))
    witness = json.loads(WITNESS.read_text(encoding="utf-8"))

    scope = {
        line[3:]
        for line in git("status", "--porcelain").splitlines()
        if line
    }
    expected = {
        line.strip()
        for line in FILELIST.read_text(encoding="utf-8").splitlines()
        if line.strip()
    }

    static_ok = True
    manifest = ROOT / "docs/F3_4D2BR1_OVERLAY_CHECKSUMS_v1.sha256"
    for line in manifest.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        digest, rel = line.split(maxsplit=1)
        static_ok &= sha256(ROOT / rel.strip()) == digest

    checks = {
        "head_exact_parent": git("rev-parse", "HEAD") == PARENT,
        "branch_main": git("branch", "--show-current") == "main",
        "ahead_zero": git("rev-list", "--count", "origin/main..HEAD") == "0",
        "behind_zero": git("rev-list", "--count", "HEAD..origin/main") == "0",
        "no_staged_changes": git("diff", "--cached", "--name-only") == "",
        "overlay_scope_exact": scope == expected,
        "static_checksums_pass": bool(static_ok),
        "cal_context_469": cfg["cal_input_extension"]["files"][
            "person_day_context"
        ]["expected_rows"] == 469,
        "cal_chain_days_319": cfg["cal_input_extension"]["files"][
            "chain_days"
        ]["expected_rows"] == 319,
        "cal_transitions_1065": cfg["cal_input_extension"]["files"][
            "chain_transitions"
        ]["expected_rows"] == 1065,
        "cal_physical_1853": cfg["cal_input_extension"][
            "physical_rows_total"
        ] == 1853,
        "train_rows_4872": witness["train_rows"] == 4872,
        "return_previous_rows_53": witness["return_previous_rows"] == 53,
        "semantic_rp_zero": witness[
            "semantic_return_previous_violations"
        ] == 0,
        "semantic_direct_zero": witness[
            "semantic_direct_mapping_violations"
        ] == 0,
        "return_eligible_1575": witness["return_eligible_rows"] == 1575,
        "global_p_exact": approx(
            witness["global_weighted_p_return_previous"],
            0.029805493179307727,
            1e-15,
        ),
        "level_rows_exact": witness["selected_level_rows"] == {
            "L1": 780,
            "L2": 184,
            "L3": 405,
            "L4": 175,
            "L5_GLOBAL": 31,
        },
        "p_zero_rows_1255": witness["selected_rows_with_p_zero"] == 1255,
        "p_one_rows_zero": witness["selected_rows_with_p_one"] == 0,
        "artifact_hash_matches": sha256(ARTIFACT)
        == witness["purpose_artifact_sha256"],
        "primitive_exact": artifact["primitive_id"]
        == "CHAIN_PURPOSE_ATTRIBUTION_V1",
        "source_n_min_30": artifact["source_n_min"] == 30,
        "smoothing_none": artifact["smoothing"] == "NONE",
        "shared_candidate_scope": artifact["candidate_scope"].startswith(
            "SHARED_IDENTICAL_PRIMITIVE"
        ),
        "candidate_identity_not_rng": artifact[
            "candidate_identity_in_rng_key"
        ] is False,
        "prop_fixed_cohort_319": cfg["propagated_observability"][
            "fixed_source_cohort"
        ]["context_row_ids"] == 319,
        "prop_no_reselection": cfg["propagated_observability"][
            "cohort_reselection_by_generated_mobile_state"
        ] is False,
        "ret_notrip_excluded": cfg["propagated_observability"]["guardrails"][
            "M2-RET-01"
        ]["no_trip_day_contribution"] == "EXCLUDED_FROM_DENOMINATOR",
        "primary_not_redefined": cfg["propagated_observability"][
            "primary_metric"
        ]["redefine_in_propagated"] is False,
        "candidate_selection_none": cfg["unchanged_science"][
            "candidate_selection"
        ] == "NONE",
        "cal_rows_zero": cfg["boundaries"]["cal_rows_read_by_this_phase"] == 0
        and witness["calibration_rows_read"] == 0,
        "real_cal_not_authorized": cfg["boundaries"][
            "real_cal_open_authorized"
        ] is False,
        "test_rows_zero": cfg["boundaries"]["test_rows_read"] == 0
        and witness["test_rows_read"] == 0,
        "test_sealed": cfg["boundaries"]["test_open_authorized"] is False,
        "g2_not_evaluated": cfg["boundaries"]["formal_g2"] == "NOT_EVALUATED",
    }
    failed = [k for k, v in checks.items() if not v]
    result = {
        "phase": "F3.4d-2b-R1",
        "status": "PASS" if not failed else "FAIL",
        "remediation_gate": "PASS" if not failed else "FAIL",
        "issues_closed_if_committed": [
            "AC-CAL-INPUT-001",
            "AC-PURPOSE-SEM-001",
            "AC-PROP-OBS-001",
        ],
        "candidate_selection": "NONE",
        "cal_rows_read": 0,
        "real_cal_open_authorized": False,
        "test_rows_read": 0,
        "test_open_authorized": False,
        "formal_g2": "NOT_EVALUATED",
        "next_step_if_pass": "COMMIT_REMEDIATION_THEN_BUILD_REAL_CAL_RUNNER_PREOPEN",
        "checks": checks,
        "failed": failed,
        "overlay_scope": {
            "expected_count": len(expected),
            "actual_count": len(scope),
            "missing": sorted(expected - scope),
            "unexpected": sorted(scope - expected),
        },
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
