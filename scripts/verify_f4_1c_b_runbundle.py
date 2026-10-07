from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
from typing import Any, cast

import yaml

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "configs/f4/f4_1c_b_acquisition_preopen_v1.yaml"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return cast(dict[str, Any], payload)


def _required_files() -> set[str]:
    payload = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Invalid F4.1c-B config")
    raw = payload["required_runbundle"]
    if not isinstance(raw, list) or not all(isinstance(item, str) for item in raw):
        raise ValueError("Invalid required_runbundle contract")
    return set(cast(list[str], raw))


def verify_checksums(run: Path, required: set[str]) -> bool:
    manifest = run / "checksums.sha256"
    if not manifest.is_file():
        return False
    covered: set[str] = set()
    for line in manifest.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        expected, name = line.split("  ", 1)
        relative = name.strip()
        target = run / relative
        covered.add(relative)
        if not target.is_file() or sha256_file(target) != expected:
            return False
    return covered == required - {"checksums.sha256"}


def _csv_readable(path: Path) -> bool:
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.reader(handle)
        try:
            header = next(reader)
        except StopIteration:
            return False
    return bool(header) and all(bool(column.strip()) for column in header)


def validate_runbundle(run: Path) -> dict[str, Any]:
    required = _required_files()
    observed = {path.name for path in run.iterdir() if path.is_file()}
    checks: dict[str, bool] = {
        "required_files_exact": observed == required,
        "checksums_ok": verify_checksums(run, required),
    }
    if not required.issubset(observed):
        missing = sorted(required - observed)
        return {
            "phase": "F4.1c-B",
            "status": "FAIL",
            "checks": checks,
            "failed": sorted(name for name, value in checks.items() if not value),
            "missing": missing,
        }

    acquisition = _load_json(run / "acquisition_manifest.json")
    pbf = _load_json(run / "pbf_metadata.json")
    environment = _load_json(run / "environment.json")
    manifest = _load_json(run / "run_manifest.json")
    provider_md5 = (run / "provider_md5.txt").read_text(encoding="utf-8").strip()
    local_sha = (run / "local_sha256.txt").read_text(encoding="utf-8").strip()

    checks.update(
        {
            "phase_exact": manifest.get("phase") == "F4.1c-B",
            "run_status_pass": manifest.get("status") == "PASS",
            "audit_only_mode": manifest.get("mode") == "ACQUIRE_AND_AUDIT_ONLY",
            "snapshot_exact": manifest.get("source_snapshot_id")
            == "OSM_GEOFABRIK_BERLIN_2026-10-04_V1",
            "snapshot_matches_acquisition": acquisition.get("source_snapshot_id")
            == manifest.get("source_snapshot_id"),
            "sha256_format": len(local_sha) == 64
            and all(ch in "0123456789abcdef" for ch in local_sha),
            "md5_format": len(provider_md5) == 32
            and all(ch in "0123456789abcdef" for ch in provider_md5),
            "sha256_matches": acquisition.get("local_sha256") == local_sha
            == manifest.get("local_sha256")
            == pbf.get("local_sha256"),
            "md5_matches": acquisition.get("provider_md5_expected") == provider_md5
            == acquisition.get("provider_md5_observed")
            == manifest.get("provider_md5"),
            "pbf_readable": pbf.get("pbf_open_read_check") is True,
            "pbf_metadata_timestamp_audited": "pbf_header_timestamp" in pbf,
            "pbf_metadata_bbox_audited": "pbf_bbox" in pbf,
            "implementation_commit_recorded": isinstance(
                manifest.get("implementation_commit"), str
            )
            and len(cast(str, manifest.get("implementation_commit"))) == 40,
            "runtime_supply_not_materialized": manifest.get(
                "runtime_location_supply_materialized"
            )
            is False,
            "residential_anchor_not_materialized": manifest.get(
                "residential_anchor_materialized"
            )
            is False,
            "home_assignments_zero": manifest.get("home_assignments") == 0,
            "destination_assignments_zero": manifest.get("destination_assignments") == 0,
            "candidate_selection_none": manifest.get("candidate_selection") == "NONE",
            "g3_closed": manifest.get("g3_opened") is False,
            "mid_test_not_read": manifest.get("mid_test_read") is False,
            "g1_not_reopened": manifest.get("g1_reopened") is False,
            "g2_not_reopened": manifest.get("g2_reopened") is False,
            "python_3_12": str(environment.get("python", "")).startswith("3.12."),
        }
    )

    for filename in sorted(required):
        if filename.endswith(".csv"):
            checks[f"csv_readable:{filename}"] = _csv_readable(run / filename)

    forbidden_output_fragments = (
        "location_supply",
        "residential_anchor",
        "household_assignment",
        "destination_assignment",
        "candidate_score",
    )
    checks["no_operational_output_names"] = not any(
        any(fragment in name.lower() for fragment in forbidden_output_fragments)
        for name in observed
    )

    failed = sorted(name for name, value in checks.items() if not value)
    return {
        "phase": "F4.1c-B",
        "status": "PASS" if not failed else "FAIL",
        "runbundle_gate": "PASS" if not failed else "FAIL",
        "checks": checks,
        "failed": failed,
        "source_snapshot_id": manifest.get("source_snapshot_id"),
        "implementation_commit": manifest.get("implementation_commit"),
        "local_sha256": local_sha,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("run_dir")
    args = parser.parse_args()
    run = Path(args.run_dir).expanduser().resolve()
    payload = validate_runbundle(run)
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if payload["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
