from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

EXPECTED_SCENARIO = {
    "scenario_id": "F4_1D_BINDING_SMOKE_V1",
    "scenario_weekday": 3,
    "scenario_season": 2,
}
CORE = ("runtime_context_v1.csv.gz", "dgen_day_rows_v1.csv.gz", "dgen_trip_rows_v1.csv.gz")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_manifest(run: Path) -> dict[str, Any]:
    return json.loads((run / "run_manifest.json").read_text(encoding="utf-8"))


def checksums_ok(run: Path) -> bool:
    manifest = run / "checksums.sha256"
    if not manifest.is_file():
        return False
    for line in manifest.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        expected, name = line.split("  ", 1)
        path = run / name
        if not path.is_file() or sha256(path) != expected:
            return False
    return True


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-a", type=Path, required=True)
    parser.add_argument("--run-b", type=Path, required=True)
    args = parser.parse_args()
    run_a = args.run_a.resolve()
    run_b = args.run_b.resolve()
    ma = load_manifest(run_a)
    mb = load_manifest(run_b)

    hashes_a = {name: sha256(run_a / name) for name in CORE}
    hashes_b = {name: sha256(run_b / name) for name in CORE}
    checks = {
        "run_a_checksums": checksums_ok(run_a),
        "run_b_checksums": checksums_ok(run_b),
        "status_pass": ma.get("status") == "PASS" and mb.get("status") == "PASS",
        "same_commit": ma.get("git_commit") == mb.get("git_commit"),
        "same_origin": ma.get("origin_main") == mb.get("origin_main") == ma.get("git_commit"),
        "scenario_exact": ma.get("scenario") == EXPECTED_SCENARIO and mb.get("scenario") == EXPECTED_SCENARIO,
        "smoke_512": ma.get("smoke_population") == 512 and mb.get("smoke_population") == 512,
        "canonical_hashes_exact": hashes_a == hashes_b,
        "manifest_hashes_match_files": ma.get("canonical_output_sha256") == {
            "runtime_context": hashes_a[CORE[0]],
            "day_rows": hashes_a[CORE[1]],
            "trip_rows": hashes_a[CORE[2]],
        } and mb.get("canonical_output_sha256") == {
            "runtime_context": hashes_b[CORE[0]],
            "day_rows": hashes_b[CORE[1]],
            "trip_rows": hashes_b[CORE[2]],
        },
        "no_forbidden_reads": ma.get("cal_read_count") == 0 and mb.get("cal_read_count") == 0 and ma.get("mid_test_read_count") == 0 and mb.get("mid_test_read_count") == 0,
        "not_downstream_authorized": ma.get("downstream_authorized") is False and mb.get("downstream_authorized") is False,
        "no_full_100k": ma.get("full_100k_dgen_realization") is False and mb.get("full_100k_dgen_realization") is False,
        "no_spatial_or_g3": all(
            manifest.get(key) is False
            for manifest in (ma, mb)
            for key in ("s_near_executed", "s_dist_executed", "s_attr_executed", "g3_opened")
        ),
        "no_unhandled_categories": ma.get("support_audit", {}).get("unhandled_runtime_categories") == 0 and mb.get("support_audit", {}).get("unhandled_runtime_categories") == 0,
    }
    failed = sorted(name for name, passed in checks.items() if not passed)
    payload = {
        "phase": "F4.1d",
        "status": "PASS" if not failed else "FAIL",
        "checks": checks,
        "failed": failed,
        "canonical_output_sha256": hashes_a,
        "binding_smoke_downstream_authorized": False,
    }
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
