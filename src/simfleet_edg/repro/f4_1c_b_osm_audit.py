from __future__ import annotations

import argparse
import importlib.metadata
import importlib.util
import json
import platform
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

import yaml  # type: ignore[import-untyped]

from simfleet_edg.spatial.osm_audit import audit_osm_supply
from simfleet_edg.spatial.osm_registry import EligibilityRegistry
from simfleet_edg.spatial.osm_source import (
    acquire_exact_snapshot,
    read_pbf_header,
    sha256_file,
    validate_exact_dated_url,
)

EXPECTED_PBF_URL = "https://download.geofabrik.de/europe/germany/berlin-261004.osm.pbf"
EXPECTED_MD5_URL = "https://download.geofabrik.de/europe/germany/berlin-261004.osm.pbf.md5"
EXPECTED_FILENAME = "berlin-261004.osm.pbf"
EXPECTED_SNAPSHOT = "OSM_GEOFABRIK_BERLIN_2026-10-04_V1"


def _load_yaml(path: Path) -> dict[str, Any]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected YAML mapping: {path}")
    return cast(dict[str, Any], payload)


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _git(repo_root: Path, *args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=repo_root, text=True).strip()


def _check_hash(path: Path, expected: str) -> bool:
    return path.is_file() and sha256_file(path) == expected


def _environment() -> dict[str, Any]:
    package_names = ("osmium", "shapely", "pyproj", "PyYAML")
    versions: dict[str, str | None] = {}
    for package in package_names:
        try:
            versions[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            versions[package] = None
    return {
        "python": platform.python_version(),
        "python_implementation": platform.python_implementation(),
        "platform": platform.platform(),
        "packages": versions,
    }


def precheck(
    repo_root: Path,
    config_path: Path,
    *,
    check_environment: bool = True,
    check_lor: bool = True,
) -> dict[str, Any]:
    cfg = _load_yaml(config_path)
    checks: dict[str, bool] = {}

    checks["phase_exact"] = cfg.get("phase_id") == "F4.1c-B"
    source = cast(dict[str, Any], cfg["source"])
    checks["snapshot_exact"] = source.get("source_snapshot_id") == EXPECTED_SNAPSHOT
    checks["filename_exact"] = source.get("provider_filename") == EXPECTED_FILENAME
    checks["pbf_url_exact"] = source.get("pbf_url") == EXPECTED_PBF_URL
    checks["md5_url_exact"] = source.get("md5_url") == EXPECTED_MD5_URL
    checks["latest_forbidden"] = source.get("mutable_latest_alias_allowed") is False
    validate_exact_dated_url(
        str(source["pbf_url"]),
        expected_url=EXPECTED_PBF_URL,
        expected_filename=EXPECTED_FILENAME,
    )
    validate_exact_dated_url(
        str(source["md5_url"]),
        expected_url=EXPECTED_MD5_URL,
        expected_filename=EXPECTED_FILENAME + ".md5",
    )

    frozen_contracts = cast(dict[str, str], cfg["frozen_contracts"])
    frozen_hashes = cast(dict[str, str], cfg["frozen_contract_sha256"])
    for key, relative in frozen_contracts.items():
        checks[f"contract_hash:{key}"] = _check_hash(
            repo_root / relative,
            frozen_hashes[key],
        )

    registry = EligibilityRegistry.from_csv(repo_root / frozen_contracts["a3_registry"])
    checks["a3_registry_loaded"] = bool(registry.rules)

    lor = cast(dict[str, Any], cfg["frozen_lor"])
    if check_lor:
        for level in ("plr", "bzr", "pgr"):
            spec = cast(dict[str, str], lor[level])
            checks[f"lor_hash:{level}"] = _check_hash(
                repo_root / spec["path"], spec["sha256"]
            )
    else:
        checks["lor_hashes"] = True

    if check_environment:
        checks["python_3_12"] = sys.version_info[:2] == (3, 12)
        checks["osmium_importable"] = importlib.util.find_spec("osmium") is not None
        checks["shapely_importable"] = importlib.util.find_spec("shapely") is not None
        checks["pyproj_importable"] = importlib.util.find_spec("pyproj") is not None
    else:
        checks["environment"] = True

    boundary = cast(dict[str, Any], cfg["execution_boundary"])
    checks["audit_only"] = boundary.get("mode") == "AUDIT_ONLY"
    checks["runtime_materialization_forbidden"] = (
        boundary.get("operational_location_supply_materialization") == "FORBIDDEN"
    )
    checks["home_assignment_forbidden"] = boundary.get("home_assignment") == "FORBIDDEN"
    checks["destination_assignment_forbidden"] = (
        boundary.get("destination_assignment") == "FORBIDDEN"
    )

    failed = sorted(key for key, value in checks.items() if not value)
    return {
        "phase": "F4.1c-B",
        "mode": "PRECHECK",
        "status": "PASS" if not failed else "FAIL",
        "checks": checks,
        "failed": failed,
        "environment": _environment(),
        "network_access": "NONE",
    }


def require_frozen_implementation_commit(repo_root: Path, parent: str) -> str:
    if not (repo_root / ".git").exists():
        raise RuntimeError("Official acquisition requires a real Git clone")
    branch = _git(repo_root, "branch", "--show-current")
    head = _git(repo_root, "rev-parse", "HEAD")
    status = _git(repo_root, "status", "--porcelain", "--untracked-files=all")
    if branch != "main":
        raise RuntimeError("Official acquisition requires branch main")
    if status:
        raise RuntimeError("Official acquisition requires a clean committed worktree")
    if head == parent:
        raise RuntimeError("Official acquisition requires the F4.1c-B implementation commit")
    return head


def write_checksums(output: Path) -> None:
    target = output / "checksums.sha256"
    rows = [
        f"{sha256_file(path)}  {path.name}"
        for path in sorted(output.iterdir())
        if path.is_file() and path.name != target.name
    ]
    target.write_text("\n".join(rows) + "\n", encoding="utf-8")


def acquire_and_audit(repo_root: Path, config_path: Path, output: Path) -> dict[str, Any]:
    cfg = _load_yaml(config_path)
    pre = precheck(repo_root, config_path, check_environment=True, check_lor=True)
    if pre["status"] != "PASS":
        raise RuntimeError(f"F4.1c-B precheck failed: {pre['failed']}")

    parent = str(cfg["required_parent_commit"])
    implementation_commit = require_frozen_implementation_commit(repo_root, parent)
    source = cast(dict[str, Any], cfg["source"])
    frozen = cast(dict[str, str], cfg["frozen_contracts"])
    lor = cast(dict[str, Any], cfg["frozen_lor"])
    a3_policy = _load_yaml(repo_root / frozen["a3_policy"])
    extraction_keys = cast(list[str], a3_policy["extraction_key_universe_v1"])

    output = output.resolve()
    if output.exists() and any(output.iterdir()):
        raise FileExistsError(f"RunBundle directory is not empty: {output}")
    output.mkdir(parents=True, exist_ok=True)
    log_path = output / "run.log"

    def log(message: str) -> None:
        timestamp = datetime.now(UTC).isoformat()
        with log_path.open("a", encoding="utf-8") as handle:
            handle.write(f"{timestamp} {message}\n")

    log("F4.1c-B acquire-and-audit start")
    raw_target = repo_root / str(source["raw_target"])
    acquisition = acquire_exact_snapshot(
        source_snapshot_id=str(source["source_snapshot_id"]),
        pbf_url=str(source["pbf_url"]),
        md5_url=str(source["md5_url"]),
        provider_filename=str(source["provider_filename"]),
        raw_target=raw_target,
    )
    acquisition_payload = acquisition.to_dict()
    acquisition_payload.update(
        {
            "upstream_dataset": source["upstream_dataset"],
            "extract_provider": source["extract_provider"],
            "provider_region": source["provider_region"],
            "provider_date_label": source["provider_date_label"],
            "license_id": source["license_id"],
            "attribution_text": source["attribution_text"],
            "acquisition_tool": "simfleet_edg.repro.f4_1c_b_osm_audit",
            "acquisition_tool_version": "1",
            "implementation_commit": implementation_commit,
        }
    )
    _write_json(output / "acquisition_manifest.json", acquisition_payload)
    _write_json(raw_target.parent / "acquisition_manifest.json", acquisition_payload)
    (output / "provider_md5.txt").write_text(
        acquisition.provider_md5_expected + "\n", encoding="utf-8"
    )
    (output / "local_sha256.txt").write_text(
        acquisition.local_sha256 + "\n", encoding="utf-8"
    )
    log(f"raw source ready sha256={acquisition.local_sha256}")

    pbf_metadata = read_pbf_header(raw_target)
    pbf_metadata.update(
        {
            "source_snapshot_id": source["source_snapshot_id"],
            "file_size_bytes": acquisition.file_size_bytes,
            "local_sha256": acquisition.local_sha256,
        }
    )
    _write_json(output / "pbf_metadata.json", pbf_metadata)
    _write_json(output / "environment.json", _environment())
    log("PBF header read completed")

    registry = EligibilityRegistry.from_csv(repo_root / frozen["a3_registry"])
    bzr = cast(dict[str, str], lor["bzr"])
    plr = cast(dict[str, str], lor["plr"])
    audit = audit_osm_supply(
        source_path=raw_target,
        registry=registry,
        extraction_keys=extraction_keys,
        bzr_path=repo_root / bzr["path"],
        plr_path=repo_root / plr["path"],
    )
    audit.write(output)
    log("OSM audit completed")

    run_manifest: dict[str, Any] = {
        "phase": "F4.1c-B",
        "status": "PASS",
        "mode": "ACQUIRE_AND_AUDIT_ONLY",
        "source_snapshot_id": source["source_snapshot_id"],
        "implementation_commit": implementation_commit,
        "parent_commit": parent,
        "local_sha256": acquisition.local_sha256,
        "provider_md5": acquisition.provider_md5_expected,
        "audit_metrics": audit.metrics,
        "runtime_location_supply_materialized": False,
        "residential_anchor_materialized": False,
        "home_assignments": 0,
        "destination_assignments": 0,
        "candidate_selection": "NONE",
        "g3_opened": False,
        "mid_test_read": False,
        "g1_reopened": False,
        "g2_reopened": False,
    }
    _write_json(output / "run_manifest.json", run_manifest)
    log("RunBundle complete")
    write_checksums(output)
    return run_manifest


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    parser.add_argument("--out")
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--precheck", action="store_true")
    modes.add_argument("--acquire-and-audit", action="store_true")
    args = parser.parse_args()

    repo_root = Path.cwd().resolve()
    config_path = (repo_root / args.config).resolve()
    if args.precheck:
        result = precheck(repo_root, config_path)
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0 if result["status"] == "PASS" else 1

    if not args.out:
        parser.error("--out is required with --acquire-and-audit")
    result = acquire_and_audit(repo_root, config_path, repo_root / args.out)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
