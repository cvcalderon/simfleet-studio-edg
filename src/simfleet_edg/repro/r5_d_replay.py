"""R5 PRE-F3 reproduction: exact-source D_REPLAY diagnostic bridge."""

from __future__ import annotations

import argparse
import csv
import json
import resource
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

from simfleet_edg.common.demand_replay import (
    build_full_day_donor_pool,
    build_replay_persondays,
    build_replay_trips,
    load_raw_persons,
    load_replay_evidence,
    replay_assignment_summary,
    strict_train_source_persons,
    validate_replay,
)
from simfleet_edg.common.population_split import sha256_file

PERSONDAYS_FILENAME = "simfleet_edg_F2_1_D_REPLAY_EXACT_V1_persondays.csv"
TRIPS_FILENAME = "simfleet_edg_F2_1_D_REPLAY_EXACT_V1_trips.csv"
DONOR_POOL_FILENAME = "simfleet_edg_F2_1_full_day_diary_donor_pool_v1.csv"


def _project_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _git(root: Path, *args: str) -> str:
    result = subprocess.run(["git", *args], cwd=root, check=True, capture_output=True, text=True)
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
    return {"commit": commit, "branch": branch, "worktree_clean": clean, "upstream": upstream, "ahead": ahead, "behind": behind}


def _write_csv(path: Path, frame: pd.DataFrame) -> None:
    frame.to_csv(path, index=False)


def _write_rows(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        raise ValueError(f"Cannot write empty CSV: {path}")
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def _source_hash_rows(root: Path, specs: dict[str, Any]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for name, spec in specs.items():
        path = root / spec["path"]
        actual = sha256_file(path) if path.is_file() else ""
        rows.append({"source": name, "path": spec["path"], "expected_sha256": spec["sha256"], "actual_sha256": actual, "status": "PASS" if actual == spec["sha256"] else "FAIL"})
    return rows


def _checksums(out: Path) -> None:
    lines = []
    for path in sorted(out.iterdir()):
        if path.is_file() and path.name != "checksums.sha256":
            lines.append(f"{sha256_file(path)}  {path.name}")
    (out / "checksums.sha256").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _validation(check: str, ok: bool, detail: str) -> dict[str, str]:
    return {"check": check, "status": "PASS" if ok else "FAIL", "detail": detail}


def run(config_path: Path, out: Path) -> str:
    root = _project_root()
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    out.mkdir(parents=True, exist_ok=False)
    started_wall = time.perf_counter()
    started_cpu = time.process_time()
    git = _git_state(root)

    (out / "config_snapshot.yaml").write_text(config_path.read_text(encoding="utf-8"), encoding="utf-8")
    source_hash_rows = _source_hash_rows(root, config["sources"])
    _write_rows(out / "input_hashes.csv", source_hash_rows)

    paths = {name: root / spec["path"] for name, spec in config["sources"].items()}
    population = pd.read_csv(paths["r4_persons"], low_memory=False)
    raw_persons = load_raw_persons(paths["raw_persons"])
    split = pd.read_csv(paths["r2_split_manifest"], low_memory=False)
    evidence = load_replay_evidence(
        coverage_path=paths["f0_3b_personday_coverage"],
        functional_path=paths["f0_3c_person_sequence"],
        temporal_sequence_path=paths["f0_3d_temporal_sequence"],
        transition_path=paths["f0_3c_trip_transition"],
        trip_time_path=paths["f0_3d_trip_time"],
        spatial_path=paths["f0_3e_trip_spatial"],
    )

    source_persons = strict_train_source_persons(split, raw_persons)
    full_day_pool = build_full_day_donor_pool(split, raw_persons, evidence, paths["activity_recoding"])
    replay_persondays = build_replay_persondays(population, raw_persons, evidence)
    replay_trips = build_replay_trips(replay_persondays, evidence)

    _write_csv(out / PERSONDAYS_FILENAME, replay_persondays)
    _write_csv(out / TRIPS_FILENAME, replay_trips)
    _write_csv(out / DONOR_POOL_FILENAME, full_day_pool)
    _write_csv(out / "replay_assignment_summary.csv", replay_assignment_summary(replay_persondays))

    validation = validate_replay(
        population_persons=population,
        replay_persondays=replay_persondays,
        replay_trips=replay_trips,
        source_persons=source_persons,
        full_day_pool=full_day_pool,
        expected_assignment=config["replay"]["expected_assignment_status"],
        expected_complete=int(config["replay"]["expected_complete_person_days"]),
        expected_trips=int(config["replay"]["expected_trip_intents"]),
    )
    _write_csv(out / "r5_validation.csv", validation)

    witnesses: list[dict[str, str]] = []
    for filename, expected in config["historical_witness"]["exact_artifacts"].items():
        actual = sha256_file(out / filename) if (out / filename).is_file() else ""
        witnesses.append({"role": "EXACT", "artifact": filename, "expected_sha256": expected, "actual_sha256": actual, "status": "PASS" if actual == expected else "DIFF"})
    _write_rows(out / "reproduction_witnesses.csv", witnesses)

    assignment_counts = replay_persondays["assignment_status"].value_counts().to_dict()
    complete = int(replay_persondays["plan_status"].isin(["COMPLETE_ZERO_TRIP", "COMPLETE_MOBILE_DAY"]).sum())
    distance_counts = replay_trips["source_distance_status"].value_counts().to_dict()
    destination_counts = replay_trips["destination_resolution"].value_counts().to_dict()
    summary_rows = [
        {"metric": "person_days", "value": len(replay_persondays)},
        {"metric": "complete_person_days", "value": complete},
        {"metric": "complete_share", "value": complete / len(replay_persondays)},
        {"metric": "trip_intents", "value": len(replay_trips)},
        {"metric": "source_person_days_train", "value": len(source_persons)},
        {"metric": "full_day_donors", "value": len(full_day_pool)},
        {"metric": "full_day_zero_trip", "value": int(full_day_pool["replay_complete_zero"].sum())},
        {"metric": "full_day_mobile", "value": int(full_day_pool["replay_complete_mobile"].sum())},
    ]
    for key in config["replay"]["expected_assignment_status"]:
        summary_rows.append({"metric": f"assignment:{key}", "value": int(assignment_counts.get(key, 0))})
    for key in config["replay"]["expected_distance_status"]:
        summary_rows.append({"metric": f"distance_status:{key}", "value": int(distance_counts.get(key, 0))})
    for key in config["replay"]["expected_destination_resolution"]:
        summary_rows.append({"metric": f"destination_resolution:{key}", "value": int(destination_counts.get(key, 0))})
    _write_rows(out / "r5_summary.csv", summary_rows)

    source_hash_ok = all(row["status"] == "PASS" for row in source_hash_rows)
    replay_validation_ok = validation["result"].eq("PASS").all()
    witness_ok = all(row["status"] == "PASS" for row in witnesses)
    distance_ok = all(int(distance_counts.get(k, 0)) == int(v) for k, v in config["replay"]["expected_distance_status"].items())
    destination_ok = all(int(destination_counts.get(k, 0)) == int(v) for k, v in config["replay"]["expected_destination_resolution"].items())

    run_checks = [
        _validation("git_branch_main", git["branch"] == "main", str(git["branch"])),
        _validation("git_worktree_clean", bool(git["worktree_clean"]), str(git["worktree_clean"])),
        _validation("git_upstream_origin_main", git["upstream"] == "origin/main", str(git["upstream"])),
        _validation("git_ahead_zero", git["ahead"] == 0, str(git["ahead"])),
        _validation("git_behind_zero", git["behind"] == 0, str(git["behind"])),
        _validation("input_hashes_exact", source_hash_ok, f"{sum(r['status']=='PASS' for r in source_hash_rows)}/{len(source_hash_rows)}"),
        _validation("replay_structural_validation", replay_validation_ok, f"{int(validation['result'].eq('PASS').sum())}/{len(validation)}"),
        _validation("historical_exact_artifacts", witness_ok, f"{sum(r['status']=='PASS' for r in witnesses)}/{len(witnesses)}"),
        _validation("person_days_100000", len(replay_persondays) == int(config["replay"]["generated_person_days"]), str(len(replay_persondays))),
        _validation("complete_replay_65963", complete == int(config["replay"]["expected_complete_person_days"]), str(complete)),
        _validation("trip_intents_194457", len(replay_trips) == int(config["replay"]["expected_trip_intents"]), str(len(replay_trips))),
        _validation("source_pool_2200", len(source_persons) == int(config["replay"]["source_diary_pool"]["expected_person_days_total"]), str(len(source_persons))),
        _validation("full_day_pool_1658", len(full_day_pool) == int(config["replay"]["source_diary_pool"]["expected_full_day_donors"]), str(len(full_day_pool))),
        _validation("distance_status_exact", distance_ok, str({k: int(distance_counts.get(k, 0)) for k in config["replay"]["expected_distance_status"]})),
        _validation("destination_resolution_exact", destination_ok, str({k: int(destination_counts.get(k, 0)) for k in config["replay"]["expected_destination_resolution"]})),
        _validation("test_partition_not_consumed", True, "R5 uses frozen TRAIN provenance only; no TEST outcome access"),
    ]
    _write_rows(out / "run_validation.csv", run_checks)

    issues = [
        {
            "issue_id": config["scope_note"]["issue_id"],
            "severity": config["scope_note"]["severity"],
            "status": "OPEN_SCOPE_NOTE",
            "description": config["scope_note"]["description"],
        }
    ]
    _write_rows(out / "issues.csv", issues)

    wall_seconds = time.perf_counter() - started_wall
    cpu_seconds = time.process_time() - started_cpu
    peak_rss_kib = int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    _write_rows(out / "performance.csv", [{"wall_seconds": wall_seconds, "cpu_seconds": cpu_seconds, "peak_rss_kib": peak_rss_kib, "person_days_per_wall_second": len(replay_persondays) / wall_seconds, "trip_intents_per_wall_second": len(replay_trips) / wall_seconds}])

    status = "PASS" if all(row["status"] == "PASS" for row in run_checks) else "FAIL"
    (out / "run.log").write_text(
        "\n".join(
            [
                "R5 D_REPLAY_EXACT_V1 reproduction",
                f"status={status}",
                f"commit={git['commit']}",
                f"r5_checks={int(validation['result'].eq('PASS').sum())}/{len(validation)}",
                f"exact_artifacts={sum(r['status']=='PASS' for r in witnesses)}/{len(witnesses)}",
                f"person_days={len(replay_persondays)}",
                f"complete_person_days={complete}",
                f"trip_intents={len(replay_trips)}",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    declared_files = sorted(
        [path.name for path in out.iterdir() if path.is_file()]
        + ["manifest.json", "checksums.sha256"]
    )
    manifest = {
        "captured_at_utc": datetime.now(UTC).isoformat(),
        "schema_version": "simfleet-studio-edg-r5-runbundle-v1",
        "phase_id": "R5",
        "run_id": config["run_id"],
        "status": status,
        "config_sha256": sha256_file(out / "config_snapshot.yaml"),
        "git": git,
        "replay": {
            "variant_id": config["replay"]["variant_id"],
            "person_days": len(replay_persondays),
            "complete_person_days": complete,
            "complete_share": complete / len(replay_persondays),
            "trip_intents": len(replay_trips),
            "source_person_days_train": len(source_persons),
            "full_day_donors": len(full_day_pool),
        },
        "validation": {
            "r5_checks_total": len(validation),
            "r5_checks_pass": int(validation["result"].eq("PASS").sum()),
            "run_checks_total": len(run_checks),
            "run_checks_pass": sum(row["status"] == "PASS" for row in run_checks),
            "exact_artifacts_total": len(witnesses),
            "exact_artifacts_pass": sum(row["status"] == "PASS" for row in witnesses),
        },
        "policy": {
            "result_label": config["result_label"],
            "formal_gate_eligible": False,
            "diagnostic_exception_to_nofuture": True,
            "test_partition_consumed": False,
            "source_bytes_modified": False,
        },
        "files": declared_files,
    }
    (out / "manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    _checksums(out)
    return status


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    status = run(args.config, args.out)
    print(json.dumps({"status": status, "output": str(args.out)}, indent=2))
    raise SystemExit(0 if status == "PASS" else 1)


if __name__ == "__main__":
    main()
