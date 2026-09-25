"""R2 PRE-F3 reproduction: Berlin household eligibility and frozen split."""

from __future__ import annotations

import argparse
import csv
import json
import resource
import subprocess
import time
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

from simfleet_edg.common.population_split import (
    AGE_INFR_LABELS,
    SPLIT_ORDER,
    build_berlin_household_eligibility,
    build_split_manifest,
    descendant_split_counts,
    sha256_file,
    strict_support_counts,
    write_csv,
)


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
    clean = not bool(_git(root, "status", "--porcelain"))
    upstream = None
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
        "worktree_clean": clean,
        "upstream": upstream,
        "ahead": ahead,
        "behind": behind,
    }


def _validation(check: str, ok: bool, detail: str) -> dict[str, str]:
    return {"check": check, "status": "PASS" if ok else "FAIL", "detail": detail}


def _counter_dict(counter: Counter[str]) -> dict[str, int]:
    return {name: int(counter.get(name, 0)) for name in (*SPLIT_ORDER, "UNLINKED_EXCLUDED")}


def _checksums(out: Path) -> None:
    lines = []
    for path in sorted(out.iterdir()):
        if path.is_file() and path.name != "checksums.sha256":
            lines.append(f"{sha256_file(path)}  {path.name}")
    (out / "checksums.sha256").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_simple_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        raise ValueError(f"Cannot write empty CSV: {path}")
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def run(config_path: Path, out: Path) -> int:
    started = time.perf_counter()
    root = _project_root()
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    out.mkdir(parents=True, exist_ok=False)
    git = _git_state(root)

    source_specs = config["sources"]
    source_paths = {name: root / spec["path"] for name, spec in source_specs.items()}
    source_hash_rows = []
    for name, spec in source_specs.items():
        path = source_paths[name]
        actual = sha256_file(path) if path.is_file() else ""
        source_hash_rows.append(
            {
                "source": name,
                "path": spec["path"],
                "expected_sha256": spec["sha256"],
                "actual_sha256": actual,
                "status": "PASS" if actual == spec["sha256"] else "FAIL",
            }
        )

    eligibility, source_records = build_berlin_household_eligibility(
        source_paths["households"], int(config["berlin"]["BLAND"])
    )
    eligibility_path = out / "eligibility_reproduced.csv"
    write_csv(eligibility_path, eligibility)
    eligibility_hash = sha256_file(eligibility_path)

    split_cfg = config["split"]
    split_rows = build_split_manifest(
        eligibility,
        int(split_cfg["seed"]),
        {name: float(value) for name, value in split_cfg["fractions"].items()},
        split_cfg["manifest_version"],
        split_cfg["largest_remainder_tie_break"],
    )
    split_path = out / "split_manifest_reproduced.csv"
    write_csv(split_path, split_rows)
    split_manifest_hash = sha256_file(split_path)

    split_lookup = {
        str(row["source_household_id"]): row["split"] for row in split_rows
    }
    persons_counts = descendant_split_counts(
        source_paths["persons"], split_lookup, int(config["berlin"]["BLAND"])
    )
    trips_counts = descendant_split_counts(
        source_paths["trips"], split_lookup, int(config["berlin"]["BLAND"])
    )

    support = strict_support_counts(eligibility, source_records, split_lookup)
    support_rows = []
    for split_name in SPLIT_ORDER:
        for age_class in AGE_INFR_LABELS:
            for sex in (1, 2):
                support_rows.append(
                    {
                        "split": split_name,
                        "age_infr_class": age_class,
                        "sex": sex,
                        "count": support.get((split_name, age_class, sex), 0),
                    }
                )
    _write_simple_csv(out / "support_cells.csv", support_rows)

    all_split_counts = Counter(row["split"] for row in split_rows)
    strict_rows = [row for row in split_rows if row["joint_rmin_donor_eligible"]]
    strict_split_counts = Counter(row["split"] for row in strict_rows)
    class_counts = Counter(row["class"] for row in eligibility)
    strict_size_counts = Counter(
        str(row["household_size_class"])
        for row in eligibility
        if row["joint_rmin_donor_eligible"]
    )
    private_count = sum(bool(row["is_private_household"]) for row in eligibility)

    partial_counts: dict[str, Counter[str]] = {}
    for row in split_rows:
        if row["split_stratum"] in {"PARTIAL_6_PLUS", "PARTIAL_RMIN_MISSING", "NON_PRIVATE"}:
            partial_counts.setdefault(row["split_stratum"], Counter())[row["split"]] += 1

    descendant_rows = []
    for source_name, counter in (("Personen", persons_counts), ("Wege", trips_counts)):
        for category in (*SPLIT_ORDER, "UNLINKED_EXCLUDED", "HOUSEHOLD_NOT_FOUND"):
            descendant_rows.append(
                {"source": source_name, "category": category, "count": counter.get(category, 0)}
            )
    _write_simple_csv(out / "descendant_counts.csv", descendant_rows)

    summary_rows = [
        {"metric": "berlin_households", "value": len(eligibility)},
        {"metric": "private_households", "value": private_count},
        {"metric": "strict_rmin_households", "value": len(strict_rows)},
        {"metric": "eligibility_sha256", "value": eligibility_hash},
        {"metric": "split_manifest_sha256", "value": split_manifest_hash},
    ]
    for category, count in class_counts.items():
        summary_rows.append({"metric": f"class::{category}", "value": count})
    for split_name in SPLIT_ORDER:
        summary_rows.append({"metric": f"split_all::{split_name}", "value": all_split_counts[split_name]})
        summary_rows.append({"metric": f"split_strict::{split_name}", "value": strict_split_counts[split_name]})
    _write_simple_csv(out / "r2_summary.csv", summary_rows)
    _write_simple_csv(out / "input_hashes.csv", source_hash_rows)

    expected_elig = config["eligibility"]["expected"]
    expected_desc = config["descendants"]["expected"]
    expected_support = config["support"]["expected_min_strict_roster_support"]
    expected_partial = split_cfg["expected_partial_counts"]

    support_min = {}
    support_cell_count = {}
    for split_name in SPLIT_ORDER:
        values = [row["count"] for row in support_rows if row["split"] == split_name]
        support_min[split_name] = min(values)
        support_cell_count[split_name] = sum(value > 0 for value in values)

    validations = [
        _validation("git_branch_main", git["branch"] == "main", str(git["branch"])),
        _validation("git_worktree_clean", git["worktree_clean"], str(git["worktree_clean"])),
        _validation("git_upstream_synced", git["ahead"] == 0 and git["behind"] == 0, f"ahead={git['ahead']};behind={git['behind']}"),
        _validation("input_hashes_match_r1", all(row["status"] == "PASS" for row in source_hash_rows), f"{sum(row['status'] == 'PASS' for row in source_hash_rows)}/{len(source_hash_rows)}"),
        _validation("berlin_households_exact", len(eligibility) == int(expected_elig["berlin_households"]), f"{len(eligibility)}"),
        _validation("private_households_exact", private_count == int(expected_elig["private_households"]), f"{private_count}"),
        _validation("strict_rmin_households_exact", len(strict_rows) == int(expected_elig["strict_rmin_households"]), f"{len(strict_rows)}"),
        _validation("eligibility_class_counts_exact", dict(class_counts) == {k: int(v) for k, v in expected_elig["class_counts"].items()}, json.dumps(dict(class_counts), sort_keys=True)),
        _validation("strict_size_counts_exact", dict(strict_size_counts) == {str(k): int(v) for k, v in expected_elig["strict_household_size_counts"].items()}, json.dumps(dict(strict_size_counts), sort_keys=True)),
        _validation("eligibility_artifact_hash_exact", eligibility_hash == expected_elig["reference_eligibility_sha256"], eligibility_hash),
        _validation("split_manifest_hash_exact", split_manifest_hash == split_cfg["expected_manifest_sha256"], split_manifest_hash),
        _validation("all_split_counts_exact", dict(all_split_counts) == {k: int(v) for k, v in split_cfg["expected_all_counts"].items()}, json.dumps(dict(all_split_counts), sort_keys=True)),
        _validation("strict_split_counts_exact", dict(strict_split_counts) == {k: int(v) for k, v in split_cfg["expected_strict_counts"].items()}, json.dumps(dict(strict_split_counts), sort_keys=True)),
        _validation("partial_strata_counts_exact", all(dict(partial_counts.get(st, Counter())) == {k: int(v) for k, v in expected.items()} for st, expected in expected_partial.items()), json.dumps({k: dict(v) for k, v in partial_counts.items()}, sort_keys=True)),
        _validation("personen_descendants_exact", _counter_dict(persons_counts) == {k: int(v) for k, v in expected_desc["Personen"].items()}, json.dumps(_counter_dict(persons_counts), sort_keys=True)),
        _validation("wege_descendants_exact", _counter_dict(trips_counts) == {k: int(v) for k, v in expected_desc["Wege"].items()}, json.dumps(_counter_dict(trips_counts), sort_keys=True)),
        _validation("no_descendant_household_not_found", persons_counts.get("HOUSEHOLD_NOT_FOUND", 0) == 0 and trips_counts.get("HOUSEHOLD_NOT_FOUND", 0) == 0, f"Personen={persons_counts.get('HOUSEHOLD_NOT_FOUND', 0)};Wege={trips_counts.get('HOUSEHOLD_NOT_FOUND', 0)}"),
        _validation("support_cells_nonempty_22_each", all(support_cell_count[name] == int(config["support"]["expected_cells_per_split"]) for name in SPLIT_ORDER), json.dumps(support_cell_count, sort_keys=True)),
        _validation("support_minima_exact", support_min == {k: int(v) for k, v in expected_support.items()}, json.dumps(support_min, sort_keys=True)),
    ]
    _write_simple_csv(out / "r2_validation.csv", validations)

    overall = "PASS" if all(row["status"] == "PASS" for row in validations) else "FAIL"
    config_snapshot = out / "config_snapshot.yaml"
    config_snapshot.write_text(config_path.read_text(encoding="utf-8"), encoding="utf-8")

    wall_seconds = time.perf_counter() - started
    peak_rss_kib = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    _write_simple_csv(
        out / "performance.csv",
        [{"wall_seconds": f"{wall_seconds:.6f}", "peak_rss_kib": peak_rss_kib}],
    )

    manifest = {
        "schema_version": "simfleet-studio-edg-r2-runbundle-v1",
        "phase_id": "R2",
        "run_id": config["run_id"],
        "status": overall,
        "captured_at_utc": datetime.now(UTC).isoformat(),
        "git": git,
        "config_sha256": sha256_file(config_path),
        "input_hashes": {row["source"]: row["actual_sha256"] for row in source_hash_rows},
        "reproduced": {
            "berlin_households": len(eligibility),
            "private_households": private_count,
            "strict_rmin_households": len(strict_rows),
            "eligibility_sha256": eligibility_hash,
            "split_manifest_sha256": split_manifest_hash,
            "split_counts": dict(all_split_counts),
            "strict_split_counts": dict(strict_split_counts),
            "persons_descendants": _counter_dict(persons_counts),
            "trips_descendants": _counter_dict(trips_counts),
            "min_strict_roster_support": support_min,
        },
        "policies": config["policies"],
        "files": [
            "config_snapshot.yaml",
            "input_hashes.csv",
            "eligibility_reproduced.csv",
            "split_manifest_reproduced.csv",
            "descendant_counts.csv",
            "support_cells.csv",
            "r2_summary.csv",
            "r2_validation.csv",
            "performance.csv",
            "manifest.json",
            "run.log",
            "checksums.sha256",
        ],
    }
    (out / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    passed = sum(row["status"] == "PASS" for row in validations)
    (out / "run.log").write_text(
        "R2 eligibility + household split reproduction\n"
        f"status={overall}\n"
        f"commit={git['commit']}\n"
        f"validation_pass={passed}/{len(validations)}\n"
        f"households={len(eligibility)}\n"
        f"private={private_count}\n"
        f"strict={len(strict_rows)}\n"
        f"split_manifest_sha256={split_manifest_hash}\n",
        encoding="utf-8",
    )
    _checksums(out)
    print(json.dumps({"status": overall, "output": str(out.resolve())}, indent=2))
    return 0 if overall == "PASS" else 1


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    raise SystemExit(run(args.config, args.out))


if __name__ == "__main__":
    main()
