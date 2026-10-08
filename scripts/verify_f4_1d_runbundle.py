from __future__ import annotations

import argparse
import csv
import gzip
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



M3_VOCAB = frozenset({"HOME", "WORK", "BUSINESS", "EDUCATION", "ESCORT", "LEISURE", "OTHER", "SHOPPING"})
AUDIT = "activity_taxonomy_projection_audit_v1.csv"
EXPECTED_RAW_COUNTS = {
    "raw_private_errand_origin_rows": 132,
    "raw_private_errand_destination_rows": 144,
    "raw_private_errand_final_activity_days": 12,
    "affected_person_days": 98,
    "affected_trip_rows": 243,
    "audit_day_rows": 512,
    "audit_trip_rows": 1590,
}


def _project(raw: str) -> str:
    if raw == "PRIVATE_ERRAND":
        return "OTHER"
    if raw in M3_VOCAB:
        return raw
    raise ValueError(f"Unexpected raw activity category: {raw!r}")


def _csv_rows(path: Path) -> list[dict[str, str]]:
    if path.suffix == ".gz":
        with gzip.open(path, "rt", encoding="utf-8", newline="") as stream:
            return list(csv.DictReader(stream))
    with path.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def verify_taxonomy_run(run: Path, manifest: dict[str, Any]) -> dict[str, bool]:
    """Independent output and provenance verification: never trust PASS alone."""
    audit_path = run / AUDIT
    checks: dict[str, bool] = {"projection_audit_exists": audit_path.is_file()}
    if not audit_path.is_file():
        return checks
    days = _csv_rows(run / "dgen_day_rows_v1.csv.gz")
    trips = _csv_rows(run / "dgen_trip_rows_v1.csv.gz")
    audit = _csv_rows(audit_path)
    sidecar_sha = sha256(audit_path)
    checks["projection_audit_sha_match"] = manifest.get("activity_taxonomy_projection_audit_sha256") == sidecar_sha
    checks["retained_person_day_trip_counts"] = len(days) == 512 and len(trips) == 1590
    audit_days = [r for r in audit if r["record_type"] == "DAY"]
    audit_trips = [r for r in audit if r["record_type"] == "TRIP"]
    checks["audit_exact_cardinality"] = len(audit_days) == len(days) and len(audit_trips) == len(trips) and len(audit) == len(days) + len(trips)
    dmap = {r["row_id"]: r for r in days}
    tmap = {(r["row_id"], r["trip_index"]): r for r in trips}
    checks["identity_one_to_one"] = len(dmap) == len(days) and len(tmap) == len(trips)
    checks["m3_vocabulary_only"] = all(
        r["origin_activity"] in M3_VOCAB and r["destination_activity"] in M3_VOCAB
        for r in trips
    ) and all((r["final_activity"] in M3_VOCAB or (r["final_activity"] == "" and int(r["trip_count"]) == 0)) for r in days)
    counts = {
        "raw_private_errand_origin_rows": 0,
        "raw_private_errand_destination_rows": 0,
        "raw_private_errand_final_activity_days": 0,
        "affected_person_days": 0,
        "affected_trip_rows": 0,
        "audit_day_rows": len(audit_days),
        "audit_trip_rows": len(audit_trips),
    }
    affected: set[str] = set()
    changed_trips: set[tuple[str, str]] = set()
    provenance_ok = True
    for r in audit_days:
        d = dmap.get(r["row_id"])
        raw = r["raw_final_activity"]
        try:
            projected = "" if raw == "" and d is not None and int(d["trip_count"]) == 0 else _project(raw)
        except ValueError:
            provenance_ok = False
            continue
        provenance_ok &= d is not None and r["trip_index"] == "" and r["projected_final_activity"] == projected and d["final_activity"] == projected
        provenance_ok &= not any(r[c] for c in ("raw_origin_activity", "raw_destination_activity", "projected_origin_activity", "projected_destination_activity"))
        if raw != projected:
            counts["raw_private_errand_final_activity_days"] += 1
            affected.add(r["row_id"])
    for r in audit_trips:
        key = (r["row_id"], r["trip_index"])
        trip = tmap.get(key)
        try:
            projected_origin = _project(r["raw_origin_activity"])
            projected_destination = _project(r["raw_destination_activity"])
        except ValueError:
            provenance_ok = False
            continue
        provenance_ok &= (
            trip is not None
            and trip["origin_activity"] == projected_origin
            and trip["destination_activity"] == projected_destination
            and r["projected_origin_activity"] == projected_origin
            and r["projected_destination_activity"] == projected_destination
            and not r["raw_final_activity"]
            and not r["projected_final_activity"]
        )
        counts["raw_private_errand_origin_rows"] += int(r["raw_origin_activity"] != projected_origin)
        counts["raw_private_errand_destination_rows"] += int(r["raw_destination_activity"] != projected_destination)
        if r["raw_origin_activity"] != projected_origin or r["raw_destination_activity"] != projected_destination:
            affected.add(r["row_id"])
            changed_trips.add(key)
    counts["affected_person_days"] = len(affected)
    counts["affected_trip_rows"] = len(changed_trips)
    checks["raw_projection_provenance_exact"] = provenance_ok
    checks["expected_raw_smoke_counts"] = counts == EXPECTED_RAW_COUNTS
    checks["manifest_projection_counts_match"] = (
        manifest.get("activity_taxonomy_projection") == counts
        and manifest.get("support_audit", {}).get("runtime_taxonomy_projection") == counts
    )
    return checks

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
    checks.update({f"run_a_{key}": passed for key, passed in verify_taxonomy_run(run_a, ma).items()})
    checks.update({f"run_b_{key}": passed for key, passed in verify_taxonomy_run(run_b, mb).items()})
    checks["projection_sha256_exact"] = (
        (run_a / AUDIT).is_file() and (run_b / AUDIT).is_file()
        and sha256(run_a / AUDIT) == sha256(run_b / AUDIT)
    )
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
