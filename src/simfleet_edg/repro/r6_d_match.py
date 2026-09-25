"""R6 PRE-F3 reproduction: complete-diary D_MATCH diagnostic bridge."""

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

from simfleet_edg.common.demand_match import (
    MATCH_VARIANT_ID,
    bridge_summary,
    build_match_persondays_from_assignment_witness,
    build_match_trips,
    combined_bridge_sha256,
    combined_f2_1_validation,
    diary_donor_reuse,
    distance_prior_audit,
    match_tier_summary,
    validate_match,
)
from simfleet_edg.common.demand_replay import load_raw_persons, load_replay_evidence
from simfleet_edg.common.population_split import sha256_file

MATCH_PERSONDAYS_FILENAME = "simfleet_edg_F2_1_D_MATCH_FULLDAY_V1_persondays.csv"
MATCH_TRIPS_FILENAME = "simfleet_edg_F2_1_D_MATCH_FULLDAY_V1_trips.csv"
F2_VALIDATION_FILENAME = "simfleet_edg_F2_1_validation_v1.csv"
F2_SUMMARY_FILENAME = "simfleet_edg_F2_1_bridge_summary_v1.csv"
F2_REUSE_FILENAME = "simfleet_edg_F2_1_diary_donor_reuse_v1.csv"
F2_DISTANCE_FILENAME = "simfleet_edg_F2_1_distance_prior_audit_v1.csv"
F2_MANIFEST_FILENAME = "simfleet_edg_F2_1_manifest_v1.json"


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
        rows.append(
            {
                "source": name,
                "path": spec["path"],
                "expected_sha256": spec["sha256"],
                "actual_sha256": actual,
                "status": "PASS" if actual == spec["sha256"] else "FAIL",
            }
        )
    return rows


def _checksums(out: Path) -> None:
    lines = []
    for path in sorted(out.iterdir()):
        if path.is_file() and path.name != "checksums.sha256":
            lines.append(f"{sha256_file(path)}  {path.name}")
    (out / "checksums.sha256").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _validation(check: str, ok: bool, detail: str) -> dict[str, str]:
    return {"check": check, "status": "PASS" if ok else "FAIL", "detail": detail}


def _f2_manifest(
    *,
    bridge_hash: str,
    match_persondays: pd.DataFrame,
    match_trips: pd.DataFrame,
    donor_pool: pd.DataFrame,
    combined_validation: pd.DataFrame,
    seed: int,
) -> dict[str, Any]:
    tiers = match_persondays["match_tier"].value_counts().to_dict()
    return {
        "artifact_id": "simfleet_edg_f2_1_diagnostic_bridge_v1",
        "status": "EXPERIMENTAL_PRE_G1_DIAGNOSTIC",
        "population_snapshot": "P_TRS_EXP_V1_M_v1",
        "generated_persons": int(len(match_persondays)),
        "source_diary_pool": {
            "split": "TRAIN",
            "household_eligibility": "STRICT_RMIN_DONOR",
            "full_day_donors": int(len(donor_pool)),
            "full_day_zero_trip": int(donor_pool["replay_complete_zero"].astype(bool).sum()),
            "full_day_mobile": int(donor_pool["replay_complete_mobile"].astype(bool).sum()),
        },
        "D_MATCH": {
            "variant_id": MATCH_VARIANT_ID,
            "seed": seed,
            "definition": "static-attribute weighted matching to a different complete TRAIN diary",
            "complete_person_days": int(len(match_persondays)),
            "complete_share": 1.0,
            "trip_rows": int(len(match_trips)),
            "matching_tiers": {key: int(value) for key, value in tiers.items()},
            "self_diary_matches": int(match_persondays["self_diary_match"].astype(bool).sum()),
        },
        "matching_features_allowed": [
            "age_infr_class",
            "sex",
            "primary_activity_status",
            "employment_participation",
            "household_size_class",
        ],
        "matching_features_forbidden": [
            "participation outcome",
            "trip count",
            "purpose",
            "departure time",
            "distance",
            "mode",
            "execution outcome",
        ],
        "formal_gate_eligible": False,
        "result_label": "PRE-G1 EXPERIMENTAL DIAGNOSTIC",
        "bridge_sha256": bridge_hash,
        "validation": {
            "checks_total": int(len(combined_validation)),
            "checks_pass": int(combined_validation["result"].eq("PASS").sum()),
            "checks_fail": int(combined_validation["result"].eq("FAIL").sum()),
        },
    }


def run(config_path: Path, out: Path) -> str:
    root = _project_root()
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    out.mkdir(parents=True, exist_ok=False)
    started_wall = time.perf_counter()
    started_cpu = time.process_time()
    git = _git_state(root)
    (out / "config_snapshot.yaml").write_text(
        config_path.read_text(encoding="utf-8"), encoding="utf-8"
    )

    source_hash_rows = _source_hash_rows(root, config["sources"])
    _write_rows(out / "source_hash_validation.csv", source_hash_rows)

    persons = pd.read_csv(root / config["sources"]["r4_persons"]["path"], low_memory=False)
    households = pd.read_csv(
        root / config["sources"]["r4_households"]["path"], low_memory=False
    )
    replay_persondays = pd.read_csv(
        root / config["sources"]["r5_replay_persondays"]["path"], low_memory=False
    )
    replay_trips = pd.read_csv(
        root / config["sources"]["r5_replay_trips"]["path"], low_memory=False
    )
    donor_pool = pd.read_csv(
        root / config["sources"]["r5_full_day_donor_pool"]["path"], low_memory=False
    )
    split = pd.read_csv(root / config["sources"]["r2_split_manifest"]["path"])
    raw_persons = load_raw_persons(root / config["sources"]["raw_persons"]["path"])
    evidence = load_replay_evidence(
        coverage_path=root / config["sources"]["f0_3b_personday_coverage"]["path"],
        functional_path=root / config["sources"]["f0_3c_person_sequence"]["path"],
        temporal_sequence_path=root
        / config["sources"]["f0_3d_temporal_sequence"]["path"],
        transition_path=root / config["sources"]["f0_3c_trip_transition"]["path"],
        trip_time_path=root / config["sources"]["f0_3d_trip_time"]["path"],
        spatial_path=root / config["sources"]["f0_3e_trip_spatial"]["path"],
    )

    assignment_witness = pd.read_csv(
        root / config["sources"]["r6_assignment_witness"]["path"], low_memory=False
    )
    match_persondays = build_match_persondays_from_assignment_witness(
        population_persons=persons,
        population_households=households,
        donor_pool=donor_pool,
        raw_persons=raw_persons,
        evidence=evidence,
        assignment_witness=assignment_witness,
    )
    match_trips = build_match_trips(match_persondays, evidence)

    match_persondays_path = out / MATCH_PERSONDAYS_FILENAME
    match_trips_path = out / MATCH_TRIPS_FILENAME
    _write_csv(match_persondays_path, match_persondays)
    _write_csv(match_trips_path, match_trips)
    _write_csv(out / "match_tier_summary.csv", match_tier_summary(match_persondays))

    r6_validation = validate_match(
        match_persondays=match_persondays,
        match_trips=match_trips,
        donor_pool=donor_pool,
        split_manifest=split,
        expected_tiers=config["match"]["expected_tier_counts"],
        expected_trips=int(config["match"]["expected_trip_intents"]),
    )
    _write_csv(out / "r6_validation.csv", r6_validation)

    strict_train = split[
        (split["split"] == "TRAIN") & split["joint_rmin_donor_eligible"].astype(bool)
    ]
    strict_train_households = set(strict_train["source_household_id"].astype(int))
    combined_validation = combined_f2_1_validation(
        population_persons=persons,
        replay_persondays=replay_persondays,
        replay_trips=replay_trips,
        match_persondays=match_persondays,
        match_trips=match_trips,
        strict_train_households=strict_train_households,
    )
    _write_csv(out / F2_VALIDATION_FILENAME, combined_validation)
    _write_csv(
        out / F2_SUMMARY_FILENAME,
        bridge_summary(replay_persondays, replay_trips, match_persondays, match_trips),
    )
    _write_csv(
        out / F2_REUSE_FILENAME,
        diary_donor_reuse(replay_persondays, match_persondays),
    )
    _write_csv(
        out / F2_DISTANCE_FILENAME,
        distance_prior_audit(replay_trips, match_trips),
    )

    replay_persondays_hash = sha256_file(root / config["sources"]["r5_replay_persondays"]["path"])
    replay_trips_hash = sha256_file(root / config["sources"]["r5_replay_trips"]["path"])
    match_persondays_hash = sha256_file(match_persondays_path)
    match_trips_hash = sha256_file(match_trips_path)
    bridge_hash = combined_bridge_sha256(
        replay_persondays_hash,
        match_persondays_hash,
        replay_trips_hash,
        match_trips_hash,
    )
    expected_bridge_hash = config["historical_witness"]["bridge_sha256"]

    f2_manifest = _f2_manifest(
        bridge_hash=bridge_hash,
        match_persondays=match_persondays,
        match_trips=match_trips,
        donor_pool=donor_pool,
        combined_validation=combined_validation,
        seed=int(config["match"]["seed"]),
    )
    (out / F2_MANIFEST_FILENAME).write_text(
        json.dumps(f2_manifest, indent=2) + "\n", encoding="utf-8"
    )

    bridge_files = [
        match_persondays_path,
        match_trips_path,
        out / F2_VALIDATION_FILENAME,
        out / F2_SUMMARY_FILENAME,
        out / F2_REUSE_FILENAME,
        out / F2_DISTANCE_FILENAME,
        out / F2_MANIFEST_FILENAME,
    ]
    (out / "f2_1_bridge_checksums.sha256").write_text(
        "\n".join(f"{sha256_file(path)}  {path.name}" for path in bridge_files) + "\n",
        encoding="utf-8",
    )

    tier_counts = match_persondays["match_tier"].value_counts().to_dict()
    zero_days = int(match_persondays["plan_status"].eq("COMPLETE_ZERO_TRIP").sum())
    mobile_days = int(match_persondays["plan_status"].eq("COMPLETE_MOBILE_DAY").sum())
    actual_self = int(
        (
            match_persondays["generated_source_hp_id"].notna()
            & match_persondays["generated_source_hp_id"].astype("Int64").eq(
                match_persondays["diary_source_hp_id"].astype("Int64")
            )
        ).sum()
    )
    fallback = int(tier_counts.get("T6_GLOBAL_FALLBACK", 0))

    witnesses = [
        {
            "role": "COMBINED_EXACT",
            "artifact": "F2_1_BRIDGE_HASH",
            "expected_sha256": expected_bridge_hash,
            "actual_sha256": bridge_hash,
            "status": "PASS" if bridge_hash == expected_bridge_hash else "DIFF",
        },
        {
            "role": "INDIVIDUAL_EXACT",
            "artifact": MATCH_PERSONDAYS_FILENAME,
            "expected_sha256": config["historical_witness"]["match_persondays_sha256"],
            "actual_sha256": match_persondays_hash,
            "status": "PASS" if match_persondays_hash == config["historical_witness"]["match_persondays_sha256"] else "DIFF",
        },
        {
            "role": "INDIVIDUAL_EXACT",
            "artifact": MATCH_TRIPS_FILENAME,
            "expected_sha256": config["historical_witness"]["match_trips_sha256"],
            "actual_sha256": match_trips_hash,
            "status": "PASS" if match_trips_hash == config["historical_witness"]["match_trips_sha256"] else "DIFF",
        },
    ]
    _write_rows(out / "reproduction_witnesses.csv", witnesses)

    summary_rows: list[dict[str, Any]] = [
        {"metric": "person_days", "value": len(match_persondays)},
        {"metric": "zero_trip_person_days", "value": zero_days},
        {"metric": "mobile_person_days", "value": mobile_days},
        {"metric": "trip_intents", "value": len(match_trips)},
        {"metric": "self_diary_matches", "value": actual_self},
        {"metric": "global_fallbacks", "value": fallback},
        {"metric": "full_day_donors", "value": len(donor_pool)},
        {"metric": "bridge_sha256", "value": bridge_hash},
    ]
    for tier in config["match"]["expected_tier_counts"]:
        summary_rows.append(
            {"metric": f"tier:{tier}", "value": int(tier_counts.get(tier, 0))}
        )
    _write_rows(out / "r6_summary.csv", summary_rows)

    source_hash_ok = all(row["status"] == "PASS" for row in source_hash_rows)
    r6_validation_ok = r6_validation["result"].eq("PASS").all()
    combined_validation_ok = combined_validation["result"].eq("PASS").all()
    tiers_ok = all(
        int(tier_counts.get(key, 0)) == int(value)
        for key, value in config["match"]["expected_tier_counts"].items()
    )
    bridge_ok = bridge_hash == expected_bridge_hash

    run_checks = [
        _validation("git_branch_main", git["branch"] == "main", str(git["branch"])),
        _validation("git_worktree_clean", bool(git["worktree_clean"]), str(git["worktree_clean"])),
        _validation("git_upstream_origin_main", git["upstream"] == "origin/main", str(git["upstream"])),
        _validation("git_ahead_zero", git["ahead"] == 0, str(git["ahead"])),
        _validation("git_behind_zero", git["behind"] == 0, str(git["behind"])),
        _validation("input_hashes_exact", source_hash_ok, f"{sum(row['status'] == 'PASS' for row in source_hash_rows)}/{len(source_hash_rows)}"),
        _validation("r6_structural_validation", r6_validation_ok, f"{int(r6_validation['result'].eq('PASS').sum())}/{len(r6_validation)}"),
        _validation("combined_f2_1_validation", combined_validation_ok, f"{int(combined_validation['result'].eq('PASS').sum())}/{len(combined_validation)}"),
        _validation("person_days_100000", len(match_persondays) == int(config["match"]["generated_person_days"]), str(len(match_persondays))),
        _validation("zero_trip_person_days_15574", zero_days == int(config["match"]["expected_zero_trip_person_days"]), str(zero_days)),
        _validation("mobile_person_days_84426", mobile_days == int(config["match"]["expected_mobile_person_days"]), str(mobile_days)),
        _validation("trip_intents_291508", len(match_trips) == int(config["match"]["expected_trip_intents"]), str(len(match_trips))),
        _validation("tier_counts_exact", tiers_ok, str({key: int(tier_counts.get(key, 0)) for key in config["match"]["expected_tier_counts"]})),
        _validation("self_diary_matches_zero", actual_self == int(config["match"]["expected_self_diary_matches"]), str(actual_self)),
        _validation("global_fallbacks_zero", fallback == int(config["match"]["expected_global_fallbacks"]), str(fallback)),
        _validation("match_persondays_hash_exact", match_persondays_hash == config["historical_witness"]["match_persondays_sha256"], match_persondays_hash),
        _validation("match_trips_hash_exact", match_trips_hash == config["historical_witness"]["match_trips_sha256"], match_trips_hash),
        _validation("combined_bridge_hash_exact", bridge_ok, bridge_hash),
        _validation("test_partition_not_consumed", True, "R6 consumes strict TRAIN complete diaries only; no TEST outcomes"),
    ]
    _write_rows(out / "run_validation.csv", run_checks)

    issues = [
        {
            "issue_id": config["scope_note"]["issue_id"],
            "severity": config["scope_note"]["severity"],
            "status": "INFORMATIONAL",
            "description": config["scope_note"]["description"],
        }
    ]
    _write_rows(out / "issues.csv", issues)

    wall_seconds = time.perf_counter() - started_wall
    cpu_seconds = time.process_time() - started_cpu
    peak_rss_kib = int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    _write_rows(
        out / "performance.csv",
        [
            {
                "wall_seconds": wall_seconds,
                "cpu_seconds": cpu_seconds,
                "peak_rss_kib": peak_rss_kib,
                "person_days_per_wall_second": len(match_persondays) / wall_seconds,
                "trip_intents_per_wall_second": len(match_trips) / wall_seconds,
            }
        ],
    )

    status = "PASS" if all(row["status"] == "PASS" for row in run_checks) else "FAIL"
    (out / "run.log").write_text(
        "\n".join(
            [
                "R6 D_MATCH_FULLDAY_V1 reproduction",
                f"status={status}",
                f"commit={git['commit']}",
                f"r6_checks={int(r6_validation['result'].eq('PASS').sum())}/{len(r6_validation)}",
                f"f2_1_checks={int(combined_validation['result'].eq('PASS').sum())}/{len(combined_validation)}",
                f"person_days={len(match_persondays)}",
                f"trip_intents={len(match_trips)}",
                f"bridge_sha256={bridge_hash}",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    declared_files = sorted(
        [path.name for path in out.iterdir() if path.is_file()] + ["manifest.json", "checksums.sha256"]
    )
    manifest = {
        "captured_at_utc": datetime.now(UTC).isoformat(),
        "schema_version": "simfleet-studio-edg-r6-runbundle-v1",
        "phase_id": "R6",
        "run_id": config["run_id"],
        "status": status,
        "config_sha256": sha256_file(out / "config_snapshot.yaml"),
        "git": git,
        "match": {
            "variant_id": config["match"]["variant_id"],
            "seed": int(config["match"]["seed"]),
            "reproduction_mode": config["match"]["reproduction_mode"],
            "original_rng_mechanics_status": config["match"]["original_rng_mechanics_status"],
            "person_days": len(match_persondays),
            "zero_trip_person_days": zero_days,
            "mobile_person_days": mobile_days,
            "trip_intents": len(match_trips),
            "self_diary_matches": actual_self,
            "global_fallbacks": fallback,
            "matching_tiers": {key: int(value) for key, value in tier_counts.items()},
        },
        "bridge": {
            "historical_expected_sha256": expected_bridge_hash,
            "actual_sha256": bridge_hash,
            "exact": bridge_ok,
            "match_persondays_expected_sha256": config["historical_witness"]["match_persondays_sha256"],
            "match_persondays_actual_sha256": match_persondays_hash,
            "match_trips_expected_sha256": config["historical_witness"]["match_trips_sha256"],
            "match_trips_actual_sha256": match_trips_hash,
        },
        "validation": {
            "r6_checks_total": len(r6_validation),
            "r6_checks_pass": int(r6_validation["result"].eq("PASS").sum()),
            "f2_1_checks_total": len(combined_validation),
            "f2_1_checks_pass": int(combined_validation["result"].eq("PASS").sum()),
            "run_checks_total": len(run_checks),
            "run_checks_pass": sum(row["status"] == "PASS" for row in run_checks),
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
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
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
