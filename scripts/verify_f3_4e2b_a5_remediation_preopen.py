from __future__ import annotations

import csv
import hashlib
import json
import subprocess
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
PARENT = "0ab96825486ca8111af95eb7d7594ea16c048d96"
FILELIST = ROOT / "docs/F3_4E2B_A5_REMEDIATION_FILELIST_v1.txt"
CHECKSUMS = ROOT / "docs/F3_4E2B_A5_REMEDIATION_CHECKSUMS_v1.sha256"
OVERLAY_CHECKSUMS = ROOT / "docs/F3_4E2B_OVERLAY_CHECKSUMS_v1.sha256"
SOURCE = ROOT / "src/simfleet_edg/evaluation/time_schedule_cal_real.py"
TESTS = ROOT / "tests/test_f3_4e2b_time_schedule_real_cal_preopen.py"
CONFIG = ROOT / "configs/f3/f3_4e2b_time_schedule_real_cal_preopen_v1.yaml"
CONTRACT_DOC = ROOT / "docs/F3_4E2B_TIME_SCHEDULE_REAL_CAL_PREOPEN_v1.md"
REGISTRY = ROOT / "docs/F3_3_CANDIDATE_ARTIFACT_REGISTRY_v1.csv"


def git(*args: str) -> str:
    return subprocess.check_output(["git", "-C", str(ROOT), *args], text=True).rstrip("\n")


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def manifest_pass(path: Path) -> bool:
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        expected, rel = line.split(maxsplit=1)
        if sha(ROOT / rel.strip()) != expected:
            return False
    return True


def main() -> None:
    expected = sorted(x for x in FILELIST.read_text(encoding="utf-8").splitlines() if x)
    status = git("status", "--porcelain").splitlines()
    actual = sorted(line[3:] for line in status if line and not line.startswith("!!"))
    cfg = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    source = SOURCE.read_text(encoding="utf-8")
    tests = TESTS.read_text(encoding="utf-8")
    contract_doc = CONTRACT_DOC.read_text(encoding="utf-8")
    with REGISTRY.open(encoding="utf-8", newline="") as fh:
        rows = [r for r in csv.DictReader(fh) if r["component"] == "DG_TIME_SCHEDULE"]

    time_seed_slice = source[source.index("def _time_seed"):source.index("def _candidate_feature_columns")]
    isolated_start = source.index("def _generate_isolated_candidate")
    isolated_end = source.index("def _primary_and_auxiliary")
    isolated = source[isolated_start:isolated_end]
    propagated_start = source.index("def _run_propagated_time")
    propagated_end = source.index("def _run_controlled_time_schedule_cal_direct")
    propagated = source[propagated_start:propagated_end]

    checks = {
        "head_exact_parent": git("rev-parse", "HEAD") == PARENT,
        "branch_main": git("branch", "--show-current") == "main",
        "ahead_zero": git("rev-list", "--count", "origin/main..HEAD") == "0",
        "behind_zero": git("rev-list", "--count", "HEAD..origin/main") == "0",
        "no_staged_changes": git("diff", "--cached", "--name-only") == "",
        "remediation_scope_exact": actual == expected,
        "remediation_checksums_pass": manifest_pass(CHECKSUMS),
        "updated_overlay_checksums_pass": manifest_pass(OVERLAY_CHECKSUMS),
        "candidate_count_7": len(rows) == 7,
        "candidate_selection_none": cfg["preopen"]["candidate_selection"] == "NONE",
        "time_b_propagated_full_chain_policy_present": "EXACT_TIME_B_FULL_CHAIN_MIN_SLACK_CONDITIONAL_V1" in source,
        "time_ref_propagated_full_chain_policy_present": "EXACT_REFERENCE_FULL_CHAIN_SUPPORT_CONDITIONAL_V1" in source,
        "time_b_propagated_dispatch_uses_lookahead": "_sample_time_b_propagated_lookahead(" in propagated,
        "time_ref_propagated_dispatch_uses_lookahead": "_sample_time_ref_propagated_lookahead(" in propagated,
        "reference_thresholds_precomputed": "_reference_full_chain_thresholds(adapter, int(generated_k.max()))" in propagated,
        "isolated_time_b_sampler_unchanged": "_sample_time_b_precomputed(" in isolated and "_sample_time_b_propagated_lookahead(" not in isolated,
        "isolated_time_ref_sampler_unchanged": "_sample_time_ref_conditioned(" in isolated and "_sample_time_ref_propagated_lookahead(" not in isolated,
        "conjunctive_gate_preserved": "propagated_pass = reference_prop_pass and incumbent_prop_pass" in source,
        "candidate_rng_forbidden": "candidate_id" not in time_seed_slice,
        "lookahead_tests_present": all(name in tests for name in [
            "test_time_b_propagated_lookahead_reserves_minimum_future_slack",
            "test_time_b_propagated_lookahead_fails_when_future_slack_is_impossible",
            "test_time_ref_propagated_lookahead_preserves_only_complete_support_paths",
        ]),
        "contract_reference_and_incumbent_requirement_preserved": "Both reference and provisional incumbent must preserve zero temporal invariant violations" in " ".join(contract_doc.split()),
        "cal_contract_still_1712": cfg["cal_input"]["expected_physical_rows"] == 1712,
        "isolated_rows_still_1243": cfg["cal_input"]["expected_isolated_time_rows"] == 1243,
        "primary_metric_unchanged": cfg["evaluation"]["primary_metric"] == "M2-TIME-01",
        "practical_margin_unchanged": float(cfg["evaluation"]["practical_margin"]) == 0.005,
        "replicates_unchanged": cfg["evaluation"]["stochastic_replicates"] == 32,
        "bootstrap_unchanged": cfg["evaluation"]["household_bootstrap_replicates"] == 1000,
        "upstream_pa1": cfg["upstream"]["participation"]["artifact_id"] == "DG_PARTICIPATION::PART_A::PA1",
        "upstream_count_ref": cfg["upstream"]["trip_count"]["artifact_id"] == "DG_TRIP_COUNT::COUNT_REF::REFERENCE",
        "upstream_cha2": cfg["upstream"]["activity_chain"]["artifact_id"] == "DG_ACTIVITY_CHAIN::CHAIN_A::CHA2",
        "distance_not_authorized": cfg["preopen"]["distance_prior_real_cal_authorized"] is False,
        "test_sealed": cfg["preopen"]["test_open_authorized"] is False,
        "g2_not_evaluated": cfg["preopen"]["formal_g2"] == "NOT_EVALUATED",
    }
    checks = {key: bool(value) for key, value in checks.items()}
    failed = [key for key, value in checks.items() if not value]
    payload = {
        "phase": "F3.4e-2b",
        "remediation": "A5_PROPAGATED_FULL_CHAIN_LOOKAHEAD_REMEDIATION_V1",
        "status": "PASS" if not failed else "FAIL",
        "remediation_precommit_gate": "PASS" if not failed else "FAIL",
        "candidate_selection": "NONE",
        "formal_g2": "NOT_EVALUATED",
        "test_open_authorized": False,
        "distance_prior_real_cal_authorized": False,
        "scope": {
            "expected_count": len(expected),
            "actual_count": len(actual),
            "missing": sorted(set(expected) - set(actual)),
            "unexpected": sorted(set(actual) - set(expected)),
        },
        "checks": checks,
        "failed": failed,
        "next_step_if_pass": "COMMIT_REMEDIATION_THEN_ISSUE_NEW_COMMIT_BOUND_A6_AUTHORIZATION",
    }
    print(json.dumps(payload, indent=2, sort_keys=True))
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
