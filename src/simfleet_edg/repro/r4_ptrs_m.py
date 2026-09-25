"""R4 PRE-F3 reproduction: P_TRS_EXP_V1 at M=100,000 persons."""

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
    "simfleet_edg_P_TRS_EXP_V1_M_households_v1.csv",
    "simfleet_edg_P_TRS_EXP_V1_M_persons_v1.csv",
    "simfleet_edg_P_TRS_EXP_V1_M_resources_v1.csv",
)
DONOR_FILENAME = "simfleet_edg_F1_3b_P_TRS_EXP_V1_M_donor_reuse_v1.csv"
ZONE_FILENAME = "simfleet_edg_F1_3b_P_TRS_EXP_V1_M_zone_allocation_v1.csv"
PRESERVATION_FILENAME = "simfleet_edg_F1_3b_P_TRS_EXP_V1_M_preservation_audit_v1.csv"
VALIDATION_FILENAME = "simfleet_edg_F1_3b_P_TRS_EXP_V1_M_validation_v1.csv"
POPULATION_MANIFEST_FILENAME = "simfleet_edg_P_TRS_EXP_V1_M_manifest_v1.json"
STABILITY_FILENAME = "simfleet_edg_F1_3b_S_vs_M_stability_v1.csv"


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


def historical_m_manifest(
    *,
    actual_persons: int,
    actual_households: int,
    actual_resource_relations: int,
    linked_persons: int,
    roster_only_persons: int,
    snapshot_hash: str,
    validation_total: int,
    validation_pass: int,
    validation_fail: int,
    config: dict[str, Any],
) -> dict[str, Any]:
    """Recreate the frozen F1.3b compact manifest, including historical perf."""
    pop = config["population"]
    generation = pop["generation"]
    geography = pop["geography"]
    historical_perf = config["historical_performance_reference"]
    return {
        "snapshot_id": "P_TRS_EXP_V1_M_v1",
        "status": "EXPERIMENTAL_PRE_G1",
        "population_variant_id": pop["population_variant_id"],
        "scale_id": pop["scale_id"],
        "target_persons": int(pop["target_persons"]),
        "actual_persons": actual_persons,
        "actual_households": actual_households,
        "actual_resource_relations": actual_resource_relations,
        "generation_algorithm": generation["algorithm"],
        "generation_seed": int(generation["seed"]),
        "zone_allocation_algorithm": geography["algorithm"],
        "zone_seed": int(geography["seed"]),
        "donor_pool": {
            "split": "TRAIN",
            "eligibility": "STRICT_RMIN_DONOR",
            "n_households": int(pop["donor_pool"]["expected_households"]),
            "household_size_scope": "1..5",
            "sampling_probability": "H_GEW normalized within donor pool",
        },
        "geography": {
            "level": "PLR",
            "allocation_basis": "Zensus private-household totals only",
            "statistically_observed_plr": 541,
            "excluded_no_stat_target_plr": ["03400831", "06200418"],
            "exclusion_semantics": "NO_STAT_TARGET; not population zero",
        },
        "enrichment": {
            "linked_generated_persons": linked_persons,
            "roster_only_generated_persons": roster_only_persons,
        },
        "reproducibility": {
            "selection_and_zone_assignment_repeatable": validation_fail == 0,
            "snapshot_sha256": snapshot_hash,
        },
        "performance": {
            "generation_wall_s": historical_perf["generation_wall_s"],
            "serialization_wall_s": historical_perf["serialization_wall_s"],
            "total_wall_s": historical_perf["total_wall_s"],
            "total_cpu_s": historical_perf["total_cpu_s"],
            "peak_rss_mb": historical_perf["peak_rss_mb"],
            "output_size_mb": historical_perf["output_size_mb"],
        },
        "formal_gate_eligible": False,
        "result_label": config["result_label"],
        "validation": {
            "checks_total": validation_total,
            "checks_pass": validation_pass,
            "checks_fail": validation_fail,
        },
    }


def _exact_witness_rows(out: Path, config: dict[str, Any]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    groups = (
        ("PRIMARY_EXACT", config["historical_witness"]["primary_artifacts"]),
        ("COMPACT_EXACT", config["historical_witness"]["compact_exact_artifacts"]),
    )
    for role, artifacts in groups:
        for filename, expected_hash in artifacts.items():
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
    for filename, expected_hash in config["historical_witness"][
        "report_only_artifact_hashes"
    ].items():
        path = out / filename
        actual_hash = sha256_file(path) if path.is_file() else ""
        rows.append(
            {
                "role": "REPORT_ONLY_BYTES",
                "artifact": filename,
                "expected_sha256": expected_hash,
                "actual_sha256": actual_hash,
                "status": "PASS" if actual_hash == expected_hash else "DIFF_ALLOWED",
            }
        )
    return rows


def _tvd_values(preservation: pd.DataFrame) -> dict[str, float]:
    result: dict[str, float] = {}
    for dimension in (
        "household_size",
        "age_infr_class",
        "sex",
        "primary_activity_status",
    ):
        result[dimension] = float(
            preservation.loc[
                (preservation["dimension"] == dimension)
                & (preservation["category"] == "__TOTAL_VARIATION_DISTANCE__"),
                "absolute_difference",
            ].iloc[0]
        )
    return result


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
        {"metric": "median_donor_replicas_used", "value": median_used_replicas(donor_reuse)},
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
    initial_peak_rss_mb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0
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

    pop = config["population"]
    generation = pop["generation"]
    geography = pop["geography"]

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

    generation_started = time.perf_counter()
    selected = weighted_exact_person_draws(
        donors, int(pop["target_persons"]), int(generation["seed"])
    )
    quotas = largest_remainder_zone_quotas(source_paths["plr_target_audit"], len(selected))
    zone_assignment = deterministic_zone_assignment(quotas, int(geography["seed"]))
    households, persons, resources = materialize_population(
        selected,
        zone_assignment,
        person_lookup,
        activity_recoding,
        pop["population_variant_id"],
        pop["scale_id"],
        int(generation["seed"]),
    )
    generation_wall = time.perf_counter() - generation_started

    serialization_started = time.perf_counter()
    for filename, frame in zip(
        PRIMARY_FILENAMES, (households, persons, resources), strict=True
    ):
        write_dataframe_csv(frame, out / filename)
    serialization_wall = time.perf_counter() - serialization_started

    primary_hashes = [sha256_file(out / filename) for filename in PRIMARY_FILENAMES]
    current_snapshot_hash = snapshot_sha256(primary_hashes)

    selected_second = weighted_exact_person_draws(
        donors, int(pop["target_persons"]), int(generation["seed"])
    )
    zone_assignment_second = deterministic_zone_assignment(quotas, int(geography["seed"]))
    second_frames = materialize_population(
        selected_second,
        zone_assignment_second,
        person_lookup,
        activity_recoding,
        pop["population_variant_id"],
        pop["scale_id"],
        int(generation["seed"]),
    )
    second_hashes = [dataframe_csv_sha256(frame) for frame in second_frames]

    donor_reuse = donor_reuse_audit(donors, selected)
    zone_audit = zone_allocation_audit(quotas)
    preservation = preservation_audit(donors, households, persons, activity_recoding)
    write_dataframe_csv(donor_reuse, out / DONOR_FILENAME)
    write_dataframe_csv(zone_audit, out / ZONE_FILENAME)
    write_dataframe_csv(preservation, out / PRESERVATION_FILENAME)

    validation_rows = validate_structural_snapshot(
        households,
        persons,
        resources,
        zone_audit,
        second_hashes,
        primary_hashes,
        config["historical_witness"]["snapshot_sha256"],
        generation["algorithm"],
        geography["algorithm"],
        scale_id="M",
        target_persons=int(pop["target_persons"]),
    )
    validation_frame = pd.DataFrame(validation_rows)
    write_dataframe_csv(validation_frame, out / VALIDATION_FILENAME)
    n_pass = int((validation_frame["result"] == "PASS").sum())
    n_fail = len(validation_frame) - n_pass

    linked = int((persons["person_enrichment_status"] == "LINKED_PERSONEN").sum())
    roster_only = int(
        (persons["person_enrichment_status"] == "ROSTER_ONLY_NO_PERSONEN").sum()
    )
    historical_manifest = historical_m_manifest(
        actual_persons=len(persons),
        actual_households=len(households),
        actual_resource_relations=len(resources),
        linked_persons=linked,
        roster_only_persons=roster_only,
        snapshot_hash=current_snapshot_hash,
        validation_total=len(validation_rows),
        validation_pass=n_pass,
        validation_fail=n_fail,
        config=config,
    )
    (out / POPULATION_MANIFEST_FILENAME).write_text(
        json.dumps(historical_manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    current_tvd = _tvd_values(preservation)
    tol = float(config["numeric_tolerance"])
    tvd_rows: list[dict[str, Any]] = []
    stability_rows: list[dict[str, Any]] = []
    numeric_statuses: list[bool] = []
    for dimension, expected_m in config["historical_preservation_tvd"].items():
        current_m = current_tvd[dimension]
        diff = abs(current_m - float(expected_m))
        tvd_ok = diff <= tol
        numeric_statuses.append(tvd_ok)
        tvd_rows.append(
            {
                "dimension": dimension,
                "historical_M_TVD": float(expected_m),
                "reproduced_M_TVD": current_m,
                "absolute_difference": diff,
                "tolerance": tol,
                "status": "PASS" if tvd_ok else "FAIL",
                "role": "NUMERIC_TOLERANCE_REPORT_ONLY_PRE_G1",
            }
        )

        s_tvd = float(config["historical_s_tvd"][dimension])
        current_delta = current_m - s_tvd
        current_ratio = current_m / s_tvd
        expected_delta = float(config["historical_stability"][dimension]["M_minus_S"])
        expected_ratio = float(config["historical_stability"][dimension]["M_to_S_ratio"])
        max_diff = max(
            diff,
            abs(current_delta - expected_delta),
            abs(current_ratio - expected_ratio),
        )
        stability_ok = max_diff <= tol
        numeric_statuses.append(stability_ok)
        stability_rows.append(
            {
                "dimension": dimension,
                "S_TVD": s_tvd,
                "M_TVD": current_m,
                "M_minus_S": current_delta,
                "M_to_S_ratio": current_ratio,
                "interpretation": "LOWER_IS_CLOSER_TO_EXPECTED_WEIGHTED_TRAIN_DONOR_DISTRIBUTION",
                "S_persons": 10000,
                "M_persons": 100000,
            }
        )
    _write_rows(out / "preservation_tvd_comparison.csv", tvd_rows)
    stability_frame = pd.DataFrame(stability_rows)
    write_dataframe_csv(stability_frame, out / STABILITY_FILENAME)

    _write_rows(
        out / "r4_summary.csv",
        _summary_rows(households, persons, resources, donor_reuse, zone_audit, current_snapshot_hash),
    )

    # Current-environment performance is report-only and intentionally separate
    # from the frozen performance values embedded in the historical F1.3b manifest.
    elapsed_wall = time.perf_counter() - started_wall
    elapsed_cpu = time.process_time() - started_cpu
    peak_rss_kib = int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    peak_rss_mb = peak_rss_kib / 1024.0
    primary_output_bytes = sum((out / filename).stat().st_size for filename in PRIMARY_FILENAMES)
    current_perf = {
        "generation_wall_s": generation_wall,
        "serialization_wall_s": serialization_wall,
        "total_wall_s": elapsed_wall,
        "total_cpu_s": elapsed_cpu,
        "peak_rss_mb": peak_rss_mb,
        "delta_peak_rss_mb": max(0.0, peak_rss_mb - initial_peak_rss_mb),
        "output_size_mb": primary_output_bytes / (1024.0 * 1024.0),
        "persons_per_generation_wall_s": len(persons) / generation_wall,
    }
    _write_rows(
        out / "performance.csv",
        [{**current_perf, "role": "REPORT_ONLY_ENVIRONMENT_DEPENDENT"}],
    )
    perf_artifact_rows = [
        {"metric": "generation_wall_s", "value": current_perf["generation_wall_s"], "notes": "Materialization before CSV serialization"},
        {"metric": "serialization_wall_s", "value": current_perf["serialization_wall_s"], "notes": "Write household/person/resource CSVs"},
        {"metric": "total_wall_s", "value": current_perf["total_wall_s"], "notes": "Full R4 tool run through audits"},
        {"metric": "total_cpu_s", "value": current_perf["total_cpu_s"], "notes": "Process CPU time"},
        {"metric": "peak_rss_mb", "value": current_perf["peak_rss_mb"], "notes": "ru_maxrss process peak; environment includes loaded source data"},
        {"metric": "delta_peak_rss_mb", "value": current_perf["delta_peak_rss_mb"], "notes": "Increase over peak already observed at start; lower-bound incremental measure"},
        {"metric": "output_size_mb", "value": current_perf["output_size_mb"], "notes": "Three primary snapshot CSV files"},
        {"metric": "households", "value": float(len(households)), "notes": ""},
        {"metric": "persons", "value": float(len(persons)), "notes": ""},
        {"metric": "resource_relations", "value": float(len(resources)), "notes": ""},
        {"metric": "persons_per_generation_wall_s", "value": current_perf["persons_per_generation_wall_s"], "notes": ""},
    ]
    _write_rows(out / "simfleet_edg_F1_3b_P_TRS_EXP_V1_M_performance_v1.csv", perf_artifact_rows)
    perf_rows = []
    for metric, historical_value in config["historical_performance_reference"].items():
        perf_rows.append(
            {
                "metric": metric,
                "historical_value": float(historical_value),
                "current_value": float(current_perf[metric]),
                "role": "REPORT_ONLY_ENVIRONMENT_DEPENDENT",
            }
        )
    _write_rows(out / "historical_performance_reference.csv", perf_rows)

    exact_witness_rows = _exact_witness_rows(out, config)
    _write_rows(out / "reproduction_witnesses.csv", exact_witness_rows)
    primary_exact_ok = all(
        row["status"] == "PASS"
        for row in exact_witness_rows
        if row["role"] == "PRIMARY_EXACT"
    )
    compact_exact_ok = all(
        row["status"] == "PASS"
        for row in exact_witness_rows
        if row["role"] == "COMPACT_EXACT"
    )

    expected_reuse = config["expected_donor_reuse"]
    source_hashes_ok = all(row["status"] == "PASS" for row in source_hash_rows)
    historical_checks_ok = n_fail == 0
    numeric_ok = all(numeric_statuses)
    max_share_error = float(zone_audit["absolute_share_error"].max())

    run_checks = [
        _validation("git_branch_main", git["branch"] == "main", str(git["branch"])),
        _validation("git_worktree_clean", bool(git["worktree_clean"]), str(git["worktree_clean"])),
        _validation(
            "git_upstream_synced",
            git["ahead"] == 0 and git["behind"] == 0,
            f"ahead={git['ahead']};behind={git['behind']}",
        ),
        _validation(
            "all_inputs_hash_match",
            source_hashes_ok,
            f"{sum(row['status'] == 'PASS' for row in source_hash_rows)}/{len(source_hash_rows)}",
        ),
        _validation("donor_pool_1219", len(donors) == int(pop["donor_pool"]["expected_households"]), str(len(donors))),
        _validation("households_56365", len(households) == int(pop["expected_households"]), str(len(households))),
        _validation("persons_100000", len(persons) == int(pop["target_persons"]), str(len(persons))),
        _validation("resources_639661", len(resources) == int(pop["expected_resource_relations"]), str(len(resources))),
        _validation("linked_persons_89459", linked == int(pop["expected_linked_persons"]), str(linked)),
        _validation("roster_only_persons_10541", roster_only == int(pop["expected_roster_only_persons"]), str(roster_only)),
        _validation("unique_donors_1213", int(donor_reuse["used"].sum()) == int(expected_reuse["unique_used"]), str(int(donor_reuse["used"].sum()))),
        _validation("max_reuse_203", int(donor_reuse["n_generated_replicas"].max()) == int(expected_reuse["max_replicas"]), str(int(donor_reuse["n_generated_replicas"].max()))),
        _validation("median_reuse_39", median_used_replicas(donor_reuse) == float(expected_reuse["median_replicas_used"]), str(median_used_replicas(donor_reuse))),
        _validation("plr_target_rows_541", int(zone_audit["source_private_households_total"].notna().sum()) == int(geography["expected_target_rows_with_value"]), str(int(zone_audit["source_private_households_total"].notna().sum()))),
        _validation("plr_positive_targets_540", int((zone_audit["source_private_households_total"].fillna(0) > 0).sum()) == int(geography["expected_positive_target_rows"]), str(int((zone_audit["source_private_households_total"].fillna(0) > 0).sum()))),
        _validation("plr_private_households_total_1960317", float(zone_audit["source_private_households_total"].sum()) == float(geography["expected_total_private_households"]), str(float(zone_audit["source_private_households_total"].sum()))),
        _validation("plr_max_share_error_exact", abs(max_share_error - float(geography["expected_max_absolute_share_error"])) <= tol, repr(max_share_error)),
        _validation("historical_primary_artifacts_exact", primary_exact_ok, f"{sum(row['status'] == 'PASS' for row in exact_witness_rows if row['role'] == 'PRIMARY_EXACT')}/3"),
        _validation("historical_compact_core_exact", compact_exact_ok, f"{sum(row['status'] == 'PASS' for row in exact_witness_rows if row['role'] == 'COMPACT_EXACT')}/4"),
        _validation("historical_validation_23_of_23", historical_checks_ok, f"{n_pass}/{len(validation_rows)}"),
        _validation("historical_snapshot_hash_exact", current_snapshot_hash == config["historical_witness"]["snapshot_sha256"], current_snapshot_hash),
        _validation("preservation_numeric_tolerance", numeric_ok, f"tolerance={tol}"),
        _validation("performance_report_only", True, "environment-dependent; no pass threshold"),
    ]
    _write_rows(out / "run_validation.csv", run_checks)

    issue = config["known_baseline_issue"]
    _write_rows(
        out / "issues.csv",
        [
            {
                "issue_id": issue["issue_id"],
                "inherited_from": issue["inherited_from"],
                "severity": issue["severity"],
                "status": "KNOWN_BASELINE_NOTE",
                "description": issue["description"],
            }
        ],
    )

    shutil.copyfile(config_path, out / "config_snapshot.yaml")

    overall_pass = all(row["status"] == "PASS" for row in run_checks)
    status = "PASS" if overall_pass else "FAIL"
    config_hash = sha256_file(config_path)
    (out / "run.log").write_text(
        "\n".join(
            [
                "R4 P_TRS_EXP_V1 M reproduction",
                f"status={status}",
                f"commit={git['commit']}",
                f"historical_checks={n_pass}/{len(validation_rows)}",
                f"snapshot_sha256={current_snapshot_hash}",
                f"persons={len(persons)}",
                f"households={len(households)}",
                f"resources={len(resources)}",
                f"generation_wall_s={generation_wall}",
                f"serialization_wall_s={serialization_wall}",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    manifest = {
        "captured_at_utc": datetime.now(UTC).isoformat(),
        "schema_version": "simfleet-studio-edg-r4-runbundle-v1",
        "phase_id": "R4",
        "run_id": config["run_id"],
        "status": status,
        "config_sha256": config_hash,
        "git": git,
        "population": {
            "variant": pop["population_variant_id"],
            "scale": pop["scale_id"],
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
            "performance_threshold_applied": False,
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
