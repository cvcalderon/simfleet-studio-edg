"""R3 PRE-F3 reproduction: P_TRS_EXP_V1 at S=10,000 persons."""

from __future__ import annotations

import argparse
import csv
import json
import resource
import shutil
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

from simfleet_edg.common.population_materializer import (
    dataframe_csv_sha256,
    deterministic_zone_assignment,
    donor_reuse_audit,
    historical_population_manifest,
    largest_remainder_zone_quotas,
    load_activity_recoding,
    load_person_lookup,
    load_source_records,
    materialize_population,
    median_used_replicas,
    preservation_audit,
    read_r2_strict_train_donors,
    snapshot_sha256,
    validate_structural_snapshot,
    weighted_exact_person_draws,
    write_dataframe_csv,
    zone_allocation_audit,
)
from simfleet_edg.common.population_split import sha256_file

PRIMARY_FILENAMES = (
    "simfleet_edg_P_TRS_EXP_V1_S_households_v1.csv",
    "simfleet_edg_P_TRS_EXP_V1_S_persons_v1.csv",
    "simfleet_edg_P_TRS_EXP_V1_S_resources_v1.csv",
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


def _write_rows(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        raise ValueError(f"Cannot write empty CSV: {path}")
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def _checksums(out: Path) -> None:
    lines = []
    for path in sorted(out.iterdir()):
        if path.is_file() and path.name != "checksums.sha256":
            lines.append(f"{sha256_file(path)}  {path.name}")
    (out / "checksums.sha256").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _source_hash_rows(root: Path, source_specs: dict[str, Any]) -> list[dict[str, str]]:
    rows = []
    for name, spec in source_specs.items():
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


def _reproduction_witness_rows(
    out: Path,
    expected_primary: dict[str, str],
    expected_compact: dict[str, str],
) -> list[dict[str, str]]:
    rows = []
    for role, expected in (
        ("PRIMARY_EXACT", expected_primary),
        ("COMPACT_REFERENCE", expected_compact),
    ):
        for filename, expected_hash in expected.items():
            path = out / filename
            actual_hash = sha256_file(path) if path.is_file() else ""
            rows.append(
                {
                    "role": role,
                    "artifact": filename,
                    "expected_sha256": expected_hash,
                    "actual_sha256": actual_hash,
                    "status": "PASS" if actual_hash == expected_hash else "DIFF",
                }
            )
    return rows


def _summary_rows(
    households: pd.DataFrame,
    persons: pd.DataFrame,
    resources: pd.DataFrame,
    donor_reuse: pd.DataFrame,
    zone_audit: pd.DataFrame,
    snapshot_hash: str,
) -> list[dict[str, Any]]:
    linked = int((persons["person_enrichment_status"] == "LINKED_PERSONEN").sum())
    roster_only = int(
        (persons["person_enrichment_status"] == "ROSTER_ONLY_NO_PERSONEN").sum()
    )
    return [
        {"metric": "persons", "value": len(persons)},
        {"metric": "households", "value": len(households)},
        {"metric": "resource_relations", "value": len(resources)},
        {"metric": "linked_persons", "value": linked},
        {"metric": "roster_only_persons", "value": roster_only},
        {"metric": "unique_donors_used", "value": int(donor_reuse["used"].sum())},
        {
            "metric": "max_donor_replicas",
            "value": int(donor_reuse["n_generated_replicas"].max()),
        },
        {
            "metric": "median_donor_replicas_used",
            "value": median_used_replicas(donor_reuse),
        },
        {
            "metric": "operational_plr_with_target_value",
            "value": int(zone_audit["source_private_households_total"].notna().sum()),
        },
        {
            "metric": "positive_plr_targets",
            "value": int((zone_audit["source_private_households_total"].fillna(0) > 0).sum()),
        },
        {
            "metric": "max_absolute_plr_share_error",
            "value": float(zone_audit["absolute_share_error"].max()),
        },
        {"metric": "snapshot_sha256", "value": snapshot_hash},
    ]


def run(config_path: Path, out: Path) -> int:
    started_wall = time.perf_counter()
    started_cpu = time.process_time()
    root = _project_root()
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    if out.exists():
        raise FileExistsError(f"Output already exists: {out}")
    out.mkdir(parents=True, exist_ok=False)

    git = _git_state(root)
    source_specs = config["sources"]
    source_hash_rows = _source_hash_rows(root, source_specs)
    _write_rows(out / "input_hashes.csv", source_hash_rows)

    source_paths = {name: root / spec["path"] for name, spec in source_specs.items()}
    population_cfg = config["population"]
    generation_cfg = population_cfg["generation"]
    geography_cfg = population_cfg["geography"]

    _, household_lookup = load_source_records(
        source_paths["households"], int(config["berlin"]["BLAND"]), "H_ID"
    )
    donors = read_r2_strict_train_donors(
        source_paths["r2_split_manifest"], household_lookup
    )
    person_lookup = load_person_lookup(
        source_paths["persons"], int(config["berlin"]["BLAND"])
    )
    activity_recoding = load_activity_recoding(source_paths["activity_recoding"])

    selected = weighted_exact_person_draws(
        donors,
        int(population_cfg["target_persons"]),
        int(generation_cfg["seed"]),
    )
    quotas = largest_remainder_zone_quotas(
        source_paths["plr_target_audit"], len(selected)
    )
    zone_assignment = deterministic_zone_assignment(
        quotas, int(geography_cfg["seed"])
    )
    households, persons, resources = materialize_population(
        selected,
        zone_assignment,
        person_lookup,
        activity_recoding,
        population_cfg["population_variant_id"],
        population_cfg["scale_id"],
        int(generation_cfg["seed"]),
    )

    primary_frames = (households, persons, resources)
    for filename, frame in zip(PRIMARY_FILENAMES, primary_frames, strict=True):
        write_dataframe_csv(frame, out / filename)
    primary_hashes = [sha256_file(out / filename) for filename in PRIMARY_FILENAMES]
    current_snapshot_hash = snapshot_sha256(primary_hashes)

    selected_second = weighted_exact_person_draws(
        donors,
        int(population_cfg["target_persons"]),
        int(generation_cfg["seed"]),
    )
    zone_assignment_second = deterministic_zone_assignment(
        quotas, int(geography_cfg["seed"])
    )
    second_frames = materialize_population(
        selected_second,
        zone_assignment_second,
        person_lookup,
        activity_recoding,
        population_cfg["population_variant_id"],
        population_cfg["scale_id"],
        int(generation_cfg["seed"]),
    )
    second_hashes = [dataframe_csv_sha256(frame) for frame in second_frames]

    donor_reuse = donor_reuse_audit(donors, selected)
    zone_audit = zone_allocation_audit(quotas)
    preservation = preservation_audit(
        donors, households, persons, activity_recoding
    )
    donor_filename = "simfleet_edg_F1_3a_P_TRS_EXP_V1_S_donor_reuse_v1.csv"
    zone_filename = "simfleet_edg_F1_3a_P_TRS_EXP_V1_S_zone_allocation_v1.csv"
    preservation_filename = (
        "simfleet_edg_F1_3a_P_TRS_EXP_V1_S_preservation_audit_v1.csv"
    )
    write_dataframe_csv(donor_reuse, out / donor_filename)
    write_dataframe_csv(zone_audit, out / zone_filename)
    write_dataframe_csv(preservation, out / preservation_filename)

    historical_tvd = config["report_only_preservation_tvd"]
    tvd_rows: list[dict[str, Any]] = []
    for dimension, expected_value in historical_tvd.items():
        current_value = float(
            preservation.loc[
                (preservation["dimension"] == dimension)
                & (preservation["category"] == "__TOTAL_VARIATION_DISTANCE__"),
                "absolute_difference",
            ].iloc[0]
        )
        tvd_rows.append(
            {
                "dimension": dimension,
                "historical_value": float(expected_value),
                "reproduced_value": current_value,
                "absolute_difference": abs(current_value - float(expected_value)),
                "role": "REPORT_ONLY_NUMERIC_WITNESS",
            }
        )
    _write_rows(out / "preservation_tvd_comparison.csv", tvd_rows)

    validation_rows = validate_structural_snapshot(
        households,
        persons,
        resources,
        zone_audit,
        second_hashes,
        primary_hashes,
        config["historical_witness"]["snapshot_sha256"],
        generation_cfg["algorithm"],
        geography_cfg["algorithm"],
    )
    validation_frame = pd.DataFrame(validation_rows)
    write_dataframe_csv(validation_frame, out / "r3_validation.csv")

    n_pass = int((validation_frame["result"] == "PASS").sum())
    n_fail = len(validation_frame) - n_pass
    linked = int((persons["person_enrichment_status"] == "LINKED_PERSONEN").sum())
    roster_only = int(
        (persons["person_enrichment_status"] == "ROSTER_ONLY_NO_PERSONEN").sum()
    )
    population_manifest = historical_population_manifest(
        target_persons=int(population_cfg["target_persons"]),
        actual_persons=len(persons),
        actual_households=len(households),
        actual_resource_relations=len(resources),
        generation_algorithm=generation_cfg["algorithm"],
        generation_seed=int(generation_cfg["seed"]),
        zone_algorithm=geography_cfg["algorithm"],
        zone_seed=int(geography_cfg["seed"]),
        donor_pool_size=len(donors),
        linked_persons=linked,
        roster_only_persons=roster_only,
        snapshot_hash=current_snapshot_hash,
    )
    population_manifest["validation"] = {
        "checks_total": len(validation_rows),
        "checks_pass": n_pass,
        "checks_fail": n_fail,
    }
    population_manifest_filename = "simfleet_edg_P_TRS_EXP_V1_S_manifest_v1.json"
    (out / population_manifest_filename).write_text(
        json.dumps(population_manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    summary_rows = _summary_rows(
        households, persons, resources, donor_reuse, zone_audit, current_snapshot_hash
    )
    _write_rows(out / "r3_summary.csv", summary_rows)

    witness_rows = _reproduction_witness_rows(
        out,
        config["historical_witness"]["primary_artifacts"],
        config["historical_witness"]["compact_artifacts"],
    )
    _write_rows(out / "reproduction_witnesses.csv", witness_rows)

    expected = population_cfg
    expected_reuse = config["expected_donor_reuse"]
    expected_geo = geography_cfg
    source_hashes_ok = all(row["status"] == "PASS" for row in source_hash_rows)
    historical_checks_ok = n_fail == 0
    primary_witnesses_ok = all(
        row["status"] == "PASS"
        for row in witness_rows
        if row["role"] == "PRIMARY_EXACT"
    )
    run_checks = [
        _validation("git_branch_main", git["branch"] == "main", str(git["branch"])),
        _validation("git_worktree_clean", bool(git["worktree_clean"]), str(git["worktree_clean"])),
        _validation(
            "git_upstream_synced",
            git["ahead"] == 0 and git["behind"] == 0,
            f"ahead={git['ahead']};behind={git['behind']}",
        ),
        _validation("all_inputs_hash_match", source_hashes_ok, f"{sum(row['status'] == 'PASS' for row in source_hash_rows)}/{len(source_hash_rows)}"),
        _validation("donor_pool_1219", len(donors) == int(expected["donor_pool"]["expected_households"]), str(len(donors))),
        _validation("households_5663", len(households) == int(expected["expected_households"]), str(len(households))),
        _validation("persons_10000", len(persons) == int(expected["target_persons"]), str(len(persons))),
        _validation("resources_64263", len(resources) == int(expected["expected_resource_relations"]), str(len(resources))),
        _validation("linked_persons_8987", linked == int(expected["expected_linked_persons"]), str(linked)),
        _validation("roster_only_persons_1013", roster_only == int(expected["expected_roster_only_persons"]), str(roster_only)),
        _validation("unique_donors_1125", int(donor_reuse["used"].sum()) == int(expected_reuse["unique_used"]), str(int(donor_reuse["used"].sum()))),
        _validation("max_reuse_25", int(donor_reuse["n_generated_replicas"].max()) == int(expected_reuse["max_replicas"]), str(int(donor_reuse["n_generated_replicas"].max()))),
        _validation("median_reuse_4", median_used_replicas(donor_reuse) == float(expected_reuse["median_replicas_used"]), str(median_used_replicas(donor_reuse))),
        _validation("plr_target_rows_541", int(zone_audit["source_private_households_total"].notna().sum()) == int(expected_geo["expected_target_rows_with_value"]), str(int(zone_audit["source_private_households_total"].notna().sum()))),
        _validation("plr_positive_targets_540", int((zone_audit["source_private_households_total"].fillna(0) > 0).sum()) == int(expected_geo["expected_positive_target_rows"]), str(int((zone_audit["source_private_households_total"].fillna(0) > 0).sum()))),
        _validation(
            "plr_private_households_total_1960317",
            float(zone_audit["source_private_households_total"].sum())
            == float(expected_geo["expected_total_private_households"]),
            str(float(zone_audit["source_private_households_total"].sum())),
        ),
        _validation(
            "historical_primary_artifacts_exact",
            primary_witnesses_ok,
            f"{sum(row['status'] == 'PASS' for row in witness_rows if row['role'] == 'PRIMARY_EXACT')}/3",
        ),
        _validation(
            "historical_validation_23_of_23",
            historical_checks_ok,
            f"{n_pass}/{len(validation_rows)}",
        ),
        _validation(
            "historical_snapshot_hash_exact",
            current_snapshot_hash == config["historical_witness"]["snapshot_sha256"],
            current_snapshot_hash,
        ),
    ]
    _write_rows(out / "run_validation.csv", run_checks)

    issue = config["known_baseline_issue"]
    _write_rows(
        out / "issues.csv",
        [
            {
                "issue_id": issue["issue_id"],
                "severity": issue["severity"],
                "status": "KNOWN_BASELINE_NOTE",
                "description": issue["description"],
            }
        ],
    )

    shutil.copyfile(config_path, out / "config_snapshot.yaml")
    elapsed_wall = time.perf_counter() - started_wall
    elapsed_cpu = time.process_time() - started_cpu
    peak_rss_kib = int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    _write_rows(
        out / "performance.csv",
        [
            {
                "wall_seconds": elapsed_wall,
                "cpu_seconds": elapsed_cpu,
                "peak_rss_kib": peak_rss_kib,
                "persons_per_wall_second": len(persons) / elapsed_wall,
            }
        ],
    )

    overall_pass = all(row["status"] == "PASS" for row in run_checks)
    status = "PASS" if overall_pass else "FAIL"
    config_hash = sha256_file(config_path)
    (out / "run.log").write_text(
        "\n".join(
            [
                "R3 P_TRS_EXP_V1 S reproduction",
                f"status={status}",
                f"commit={git['commit']}",
                f"historical_checks={n_pass}/{len(validation_rows)}",
                f"snapshot_sha256={current_snapshot_hash}",
                f"persons={len(persons)}",
                f"households={len(households)}",
                f"resources={len(resources)}",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    manifest = {
        "captured_at_utc": datetime.now(UTC).isoformat(),
        "schema_version": "simfleet-studio-edg-r3-runbundle-v1",
        "phase_id": "R3",
        "run_id": config["run_id"],
        "status": status,
        "config_sha256": config_hash,
        "git": git,
        "population": {
            "variant": population_cfg["population_variant_id"],
            "scale": population_cfg["scale_id"],
            "persons": len(persons),
            "households": len(households),
            "resource_relations": len(resources),
            "snapshot_sha256": current_snapshot_hash,
        },
        "validation": {
            "historical_checks_total": len(validation_rows),
            "historical_checks_pass": n_pass,
            "historical_checks_fail": n_fail,
            "run_checks_total": len(run_checks),
            "run_checks_pass": sum(row["status"] == "PASS" for row in run_checks),
        },
        "policy": {
            "result_label": config["result_label"],
            "formal_gate_eligible": bool(config["formal_gate_eligible"]),
            "test_partition_consumed": False,
            "source_bytes_modified": False,
        },
        "files": sorted(
            path.name
            for path in out.iterdir()
            if path.is_file() and path.name not in {"manifest.json", "checksums.sha256"}
        ),
    }
    (out / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    _checksums(out)

    print(json.dumps({"status": status, "output": str(out)}, indent=2))
    return 0 if status == "PASS" else 1


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    raise SystemExit(run(args.config, args.out))


if __name__ == "__main__":
    main()
