"""Official F1 P_CONSTR IMPL-01 source normalization and reconciliation RunBundle."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

from simfleet_edg.population.reconciliation import reconcile_all_bezirke, reconciliation_summary
from simfleet_edg.population.zensus_controls import (
    concatenate_normalized_sources,
    normalize_flat_count_zip,
    validate_fit_source_categories,
)


def _root() -> Path:
    return Path(__file__).resolve().parents[3]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _git(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=root, check=True, capture_output=True, text=True
    ).stdout.strip()


def _git_state(root: Path) -> dict[str, Any]:
    commit = _git(root, "rev-parse", "HEAD")
    branch = _git(root, "branch", "--show-current")
    status = _git(root, "status", "--porcelain")
    upstream = None
    ahead = behind = None
    try:
        upstream = _git(root, "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}")
        ahead, behind = map(
            int, _git(root, "rev-list", "--left-right", "--count", "HEAD...@{u}").split()
        )
    except subprocess.CalledProcessError:
        pass
    return {
        "commit": commit,
        "branch": branch,
        "worktree_clean": not bool(status),
        "upstream": upstream,
        "ahead": ahead,
        "behind": behind,
    }


def _load_sources(root: Path, config: dict[str, Any]):
    sources = {}
    for table_id, spec in config["sources"].items():
        sources[table_id] = normalize_flat_count_zip(
            root / spec["path"], table_id=table_id, expected_sha256=spec["sha256"]
        )
    validate_fit_source_categories(sources)
    return sources


def _write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def _checksums(out: Path) -> None:
    lines = []
    for path in sorted(item for item in out.iterdir() if item.is_file() and item.name != "checksums.sha256"):
        lines.append(f"{_sha256(path)}  {path.name}")
    (out / "checksums.sha256").write_text("\n".join(lines) + "\n", encoding="utf-8")


def run(config_path: Path, out: Path) -> int:
    start = time.perf_counter()
    root = _root()
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    if out.exists():
        raise FileExistsError(f"Official output path already exists: {out}")
    git = _git_state(root)
    if config.get("strict_git_state", True):
        if git["branch"] != "main" or not git["worktree_clean"]:
            raise RuntimeError(f"Official execution requires clean main: {git}")
        if git["ahead"] != 0 or git["behind"] != 0:
            raise RuntimeError(f"Official execution requires synchronized upstream: {git}")

    sources = _load_sources(root, config)
    normalized = concatenate_normalized_sources(sources)
    cube, audit = reconcile_all_bezirke(
        sources["1000A-3082"], sources["1000A-1029"], sources["1000A-2071"]
    )
    summary = reconciliation_summary(cube, audit)
    expected = config["expected_reconciliation"]
    validations = [
        {"check": key, "status": "PASS" if summary[key] == value else "FAIL", "observed": summary[key], "expected": value}
        for key, value in expected.items()
    ]
    validations.extend(
        [
            {
                "check": "source_rows_3082_detail_cube",
                "status": "PASS" if len(cube) == 1584 else "FAIL",
                "observed": len(cube),
                "expected": 1584,
            },
            {
                "check": "published_zero_preservation",
                "status": "PASS"
                if bool((cube.loc[cube["published_value"] == 0, "fit_target_value"] == 0).all())
                else "FAIL",
                "observed": int(
                    (cube.loc[cube["published_value"] == 0, "fit_target_value"] != 0).sum()
                ),
                "expected": 0,
            },
        ]
    )
    status = "PASS" if all(row["status"] == "PASS" for row in validations) else "FAIL"

    out.mkdir(parents=True)
    normalized.to_csv(out / "normalized_sources.csv", index=False)
    cube.to_csv(out / "reconciled_person_cube.csv", index=False)
    audit.to_csv(out / "reconciliation_audit.csv", index=False)
    _write_csv(out / "validation.csv", validations)
    (out / "config_snapshot.yaml").write_text(config_path.read_text(encoding="utf-8"), encoding="utf-8")
    elapsed = time.perf_counter() - start
    _write_csv(out / "performance.csv", [{"wall_seconds": f"{elapsed:.6f}"}])
    manifest = {
        "schema_version": "simfleet-edg-f1-pconstr-impl01-runbundle-v1",
        "phase_id": "F1-P_CONSTR-IMPL-01",
        "run_id": config["run_id"],
        "status": status,
        "captured_at_utc": datetime.now(UTC).isoformat(),
        "git": git,
        "config_sha256": _sha256(config_path),
        "source_sha256": {key: value.source_sha256 for key, value in sources.items()},
        "reconciliation_summary": summary,
        "policy": {
            "raw_source_bytes_copied_into_runbundle": False,
            "source_bytes_modified": False,
            "calibration_read": False,
            "test_read": False,
            "f3_modified": False,
        },
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (out / "run.log").write_text(
        f"F1-P_CONSTR-IMPL-01\nstatus={status}\ncommit={git['commit']}\nsummary={json.dumps(summary, sort_keys=True)}\n",
        encoding="utf-8",
    )
    _checksums(out)
    print(json.dumps({"status": status, "output": str(out.resolve()), "summary": summary}, indent=2))
    return 0 if status == "PASS" else 1


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    raise SystemExit(run(args.config.resolve(), args.out.resolve()))


if __name__ == "__main__":
    main()
