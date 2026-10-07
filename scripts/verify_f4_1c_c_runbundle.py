from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any, cast

EXPECTED_OUTPUTS = {
    "location_supply_v1.csv.gz",
    "location_supply_evidence_v1.csv.gz",
    "residential_supply_candidates_v1.csv.gz",
    "residential_anchors_v1.csv.gz",
    "residential_anchor_evidence_v1.csv.gz",
    "materialization_exclusions_v1.csv.gz",
}
EXPECTED_PURPOSE_COUNTS = {
    "BUSINESS": 21936,
    "EDUCATION": 7227,
    "LEISURE": 36463,
    "OTHER": 8602,
    "SHOPPING": 22436,
    "WORK_COMMUTE": 59344,
}
REQUIRED_RUNBUNDLE = {
    "environment.json",
    "input_identity.json",
    "output_hashes.json",
    "validation.json",
    "run_manifest.json",
    "run.log",
    "F4_1C_C_MATERIALIZATION_SUMMARY.md",
    "reproducibility.json",
    "checksums.sha256",
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected object: {path}")
    return cast(dict[str, Any], payload)


def checksums_ok(runbundle: Path) -> bool:
    manifest = runbundle / "checksums.sha256"
    if not manifest.is_file():
        return False
    covered: set[str] = set()
    for line in manifest.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        expected, name = line.split("  ", 1)
        target = runbundle / name
        covered.add(name)
        if not target.is_file() or sha256(target) != expected:
            return False
    return covered == REQUIRED_RUNBUNDLE - {"checksums.sha256"}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("runbundle")
    parser.add_argument("--output-root")
    args = parser.parse_args()

    runbundle = Path(args.runbundle).resolve()
    checks: dict[str, bool] = {}
    checks["runbundle_exists"] = runbundle.is_dir()
    if not runbundle.is_dir():
        payload = {"phase": "F4.1c-C", "status": "FAIL", "checks": checks}
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 1

    observed = {path.name for path in runbundle.iterdir() if path.is_file()}
    checks["required_files_exact"] = observed == REQUIRED_RUNBUNDLE
    checks["checksums_ok"] = checksums_ok(runbundle)

    manifest = _load_json(runbundle / "run_manifest.json")
    validation = _load_json(runbundle / "validation.json")
    hashes = _load_json(runbundle / "output_hashes.json")
    repro = _load_json(runbundle / "reproducibility.json")

    commit = str(manifest.get("implementation_commit", ""))
    checks["phase_exact"] = manifest.get("phase") == "F4.1c-C"
    checks["status_pass"] = manifest.get("status") == "PASS"
    checks["implementation_commit_sha1"] = bool(re.fullmatch(r"[0-9a-f]{40}", commit))
    checks["repro_manifest_pass"] = manifest.get("reproducibility_exact_sha256_match") is True
    checks["no_destinations"] = manifest.get("nonhome_destination_assignments") == 0
    checks["s_near_closed"] = manifest.get("s_near_executed") is False
    checks["s_dist_closed"] = manifest.get("s_dist_executed") is False
    checks["s_attr_closed"] = manifest.get("s_attr_executed") is False
    checks["g3_closed"] = manifest.get("g3_opened") is False
    checks["mid_test_closed"] = manifest.get("mid_test_read") is False

    checks["six_output_hashes"] = set(hashes) == EXPECTED_OUTPUTS
    checks["hash_format"] = all(
        isinstance(value, str) and bool(re.fullmatch(r"[0-9a-f]{64}", value))
        for value in hashes.values()
    )
    checks["repro_status_pass"] = repro.get("status") == "PASS"
    checks["repro_exact"] = repro.get("exact_sha256_match") is True
    checks["repro_reference_matches"] = repro.get("reference_hashes") == hashes
    checks["repro_second_matches"] = repro.get("second_run_hashes") == hashes

    checks["anchors_exact"] = validation.get("residential_anchors") == 54828
    checks["persons_exact"] = validation.get("persons_reusing_household_anchor") == 100000
    checks["fallback_zero"] = validation.get("residential_fallback_households") == 0
    checks["outside_operational_zero"] = validation.get("operational_outside_records") == 0
    checks["attractiveness_null"] = validation.get("attractiveness_nonnull") == 0
    checks["capacity_null"] = validation.get("capacity_nonnull") == 0
    checks["purpose_counts_exact"] = validation.get("purpose_label_counts") == EXPECTED_PURPOSE_COUNTS

    if args.output_root:
        output_root = Path(args.output_root).resolve()
        checks["output_root_exists"] = output_root.is_dir()
        if output_root.is_dir():
            observed_outputs = {path.name for path in output_root.iterdir() if path.is_file()}
            checks["output_files_exact"] = observed_outputs == EXPECTED_OUTPUTS
            checks["output_hashes_match"] = all(
                (output_root / name).is_file() and sha256(output_root / name) == digest
                for name, digest in hashes.items()
            )
        else:
            checks["output_files_exact"] = False
            checks["output_hashes_match"] = False

    failed = sorted(name for name, passed in checks.items() if not passed)
    payload = {
        "phase": "F4.1c-C",
        "status": "PASS" if not failed else "FAIL",
        "checks": checks,
        "failed": failed,
        "runbundle_gate": "PASS" if not failed else "FAIL",
    }
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
