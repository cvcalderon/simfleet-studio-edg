"""R1 PRE-F3 source audit: verify authoritative source bytes before transformations."""

from __future__ import annotations

import argparse
import csv
import json
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

from simfleet_edg.common.source_audit import inspect_source, sha256_file


def _project_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _git(root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=root, check=True, capture_output=True, text=True
    )
    return result.stdout.strip()


def _git_state(root: Path) -> dict[str, Any]:
    commit = _git(root, "rev-parse", "HEAD")
    branch = _git(root, "branch", "--show-current")
    status = _git(root, "status", "--porcelain")
    upstream = ""
    ahead = behind = None
    try:
        upstream = _git(root, "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}")
        counts = _git(root, "rev-list", "--left-right", "--count", "HEAD...@{u}").split()
        ahead, behind = map(int, counts)
    except (subprocess.CalledProcessError, ValueError):
        pass
    return {
        "commit": commit,
        "branch": branch,
        "worktree_clean": not bool(status),
        "upstream": upstream or None,
        "ahead": ahead,
        "behind": behind,
    }


def _config_hash(path: Path) -> str:
    return sha256_file(path)


def _audit_one(root: Path, spec: dict[str, Any]) -> dict[str, Any]:
    rel = Path(spec["path"])
    path = (root / rel).resolve()
    raw_root = (root / "data" / "raw").resolve()
    in_raw = raw_root == path or raw_root in path.parents
    exists = path.is_file()
    row: dict[str, Any] = {
        "source_id": spec["source_id"],
        "family": spec.get("family", ""),
        "path": str(rel),
        "kind": spec["kind"],
        "required": bool(spec.get("required", False)),
        "exists": exists,
        "path_within_data_raw": in_raw,
        "expected_sha256": spec.get("sha256", ""),
        "actual_sha256": "",
        "hash_match": False,
        "size_bytes": path.stat().st_size if exists else 0,
        "observed_rows": "",
        "observed_columns": "",
        "observed_sheets": "",
        "observed_features": "",
        "missing_required_columns": "",
        "structure_status": "NOT_CHECKED",
        "status": "MISSING" if not exists else "PENDING",
        "error": "",
    }
    if not exists:
        return row

    try:
        actual_hash = sha256_file(path)
        row["actual_sha256"] = actual_hash
        row["hash_match"] = actual_hash == spec.get("sha256")
        details = inspect_source(path, spec["kind"])
        if spec["kind"] == "csv":
            row["observed_rows"] = details["rows"]
            row["observed_columns"] = details["columns"]
            required_cols = spec.get("required_columns", [])
            missing = [name for name in required_cols if name not in details["header"]]
            row["missing_required_columns"] = ";".join(missing)
            structure_ok = (
                details["rows"] == spec.get("expected_rows")
                and details["columns"] == spec.get("expected_columns")
                and not missing
            )
        elif spec["kind"] == "xlsx":
            row["observed_sheets"] = details["sheets"]
            structure_ok = details["sheets"] == spec.get("expected_sheets")
        elif spec["kind"] == "geojson":
            row["observed_features"] = details["features"]
            structure_ok = (
                details["type"] == "FeatureCollection"
                and details["features"] == spec.get("expected_features")
            )
        elif spec["kind"] == "zip":
            structure_ok = bool(details["zip_integrity"])
        else:
            structure_ok = True
        row["structure_status"] = "PASS" if structure_ok else "FAIL"
        row["status"] = "PASS" if row["hash_match"] and structure_ok and in_raw else "FAIL"
    except Exception as exc:  # audit should preserve evidence rather than crash silently
        row["status"] = "ERROR"
        row["structure_status"] = "ERROR"
        row["error"] = f"{type(exc).__name__}: {exc}"
    return row


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(rows[0].keys()) if rows else ["status"]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _checksums(out: Path, exclude: set[str] | None = None) -> None:
    exclude = exclude or {"checksums.sha256"}
    lines = []
    for path in sorted(p for p in out.iterdir() if p.is_file() and p.name not in exclude):
        lines.append(f"{sha256_file(path)}  {path.name}")
    (out / "checksums.sha256").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _precheck(root: Path, config: dict[str, Any]) -> int:
    print("R1 source precheck")
    print(f"project_root: {root}")
    required_missing = 0
    for spec in config["sources"]:
        path = root / spec["path"]
        marker = "OK" if path.is_file() else "MISSING"
        req = "required" if spec.get("required") else "optional"
        print(f"[{marker:7}] [{req:8}] {spec['source_id']}: {spec['path']}")
        if spec.get("required") and not path.is_file():
            required_missing += 1
    print(f"required_missing: {required_missing}")
    return 0 if required_missing == 0 else 2


def run(config_path: Path, out: Path) -> int:
    start = time.perf_counter()
    root = _project_root()
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    out.mkdir(parents=True, exist_ok=True)

    git = _git_state(root)
    rows = [_audit_one(root, spec) for spec in config["sources"]]
    required = [row for row in rows if row["required"]]
    optional = [row for row in rows if not row["required"]]

    validations = [
        {
            "check": "git_branch_main",
            "status": "PASS" if git["branch"] == "main" else "FAIL",
            "detail": git["branch"],
        },
        {
            "check": "git_worktree_clean",
            "status": "PASS" if git["worktree_clean"] else "FAIL",
            "detail": str(git["worktree_clean"]),
        },
        {
            "check": "git_upstream_synced",
            "status": "PASS" if git["ahead"] == 0 and git["behind"] == 0 else "FAIL",
            "detail": f"ahead={git['ahead']};behind={git['behind']}",
        },
        {
            "check": "all_required_sources_present",
            "status": "PASS" if all(row["exists"] for row in required) else "FAIL",
            "detail": f"{sum(row['exists'] for row in required)}/{len(required)}",
        },
        {
            "check": "all_required_hashes_match",
            "status": "PASS" if all(row["hash_match"] for row in required) else "FAIL",
            "detail": f"{sum(row['hash_match'] for row in required)}/{len(required)}",
        },
        {
            "check": "all_required_structures_match",
            "status": "PASS" if all(row["structure_status"] == "PASS" for row in required) else "FAIL",
            "detail": f"{sum(row['structure_status'] == 'PASS' for row in required)}/{len(required)}",
        },
        {
            "check": "all_source_paths_scoped_to_data_raw",
            "status": "PASS" if all(row["path_within_data_raw"] for row in rows) else "FAIL",
            "detail": f"{sum(row['path_within_data_raw'] for row in rows)}/{len(rows)}",
        },
    ]

    overall = "PASS" if all(item["status"] == "PASS" for item in validations) else "FAIL"
    _write_csv(out / "source_audit.csv", rows)
    _write_csv(out / "r1_validation.csv", validations)

    config_snapshot = out / "config_snapshot.yaml"
    config_snapshot.write_text(config_path.read_text(encoding="utf-8"), encoding="utf-8")

    elapsed = time.perf_counter() - start
    _write_csv(out / "performance.csv", [{"wall_seconds": f"{elapsed:.6f}"}])

    manifest = {
        "schema_version": "simfleet-studio-edg-r1-runbundle-v1",
        "phase_id": "R1",
        "run_id": config.get("run_id", "R1_source_audit_v1"),
        "status": overall,
        "captured_at_utc": datetime.now(UTC).isoformat(),
        "git": git,
        "config_sha256": _config_hash(config_path),
        "source_counts": {
            "total": len(rows),
            "required": len(required),
            "optional": len(optional),
            "required_pass": sum(row["status"] == "PASS" for row in required),
            "optional_pass": sum(row["status"] == "PASS" for row in optional),
        },
        "policy": {
            "raw_files_copied_into_runbundle": False,
            "source_bytes_modified": False,
            "hash_algorithm": "SHA-256",
        },
        "files": [
            "config_snapshot.yaml",
            "source_audit.csv",
            "r1_validation.csv",
            "performance.csv",
            "manifest.json",
            "run.log",
        ],
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (out / "run.log").write_text(
        f"R1 source audit\nstatus={overall}\ncommit={git['commit']}\nrequired_pass={manifest['source_counts']['required_pass']}/{len(required)}\n",
        encoding="utf-8",
    )
    _checksums(out)
    print(json.dumps({"status": overall, "output": str(out.resolve())}, indent=2))
    return 0 if overall == "PASS" else 1


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--precheck", action="store_true")
    args = parser.parse_args()
    config_path = args.config.resolve()
    root = _project_root()
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    if args.precheck:
        raise SystemExit(_precheck(root, config))
    if args.out is None:
        parser.error("--out is required unless --precheck is used")
    raise SystemExit(run(config_path, args.out))


if __name__ == "__main__":
    main()
