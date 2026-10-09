"""F4.2a frozen 100k official reference runner. POST-PUSH ONLY.

NO CAL/MiD TEST, network, fitting, M1 synthesis, OSM rematerialization, mode
or route. Rejects missing frozen input, parent Git mismatch and partial data.
"""
from __future__ import annotations

import argparse
import json
import math
import platform
import resource
import subprocess
import time
from collections import Counter
from pathlib import Path
from typing import Any

import pandas as pd  # type: ignore[import-untyped]

from simfleet_edg.canonical.mobility import PersonDayPlan
from simfleet_edg.demand.m2_m3_adapter import adapt_joint_generated_frames
from simfleet_edg.demand.runtime_context import ScenarioDayContext, build_runtime_context
from simfleet_edg.demand.runtime_generator import ProductionDGenGenerator
from simfleet_edg.spatial.candidate_policies import (
    POLICIES,
    Policy,
    abs_log_ratio,
    extended_metrics,
    preregistered_promotion,
)
from simfleet_edg.spatial.spatial_core_io import (
    FrozenSupply,
    digest,
    frozen_input_gate,
    load_frozen_supply,
    write_gzip_rows,
    write_json,
)
from simfleet_edg.spatial.spatialize_core import CoreSpatialized, Spatializer

PARENT = "61f29671a1e2a562d000bd6a1be45366a6630568"
SCENARIO_ID = "F4_2A_CORE_REFERENCE_V1"
SCENARIO_DAY_ID = "F4_2A_CORE_REFERENCE_DAY_01"
M1_FILES = {
    "M_P_CONSTR_RMIN_V2_HD_U_households.csv": "99e63cd1f203f36a0a1e7096abf0cd89555615b64a421a58cbc5c5f1af2d1c1b",
    "M_P_CONSTR_RMIN_V2_HD_U_persons.csv": "e75d768637ae97c19bf34c678a99aeec4fe0e5594805ced01ac4da4e95164d49",
    "M_P_CONSTR_RMIN_V2_HD_U_resources.csv": "0d101d2a544227a13b7c7bfa108fd977c0256de3822c49f5cec61d81c557bcce",
}


def _git(root: Path, *args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=root, text=True).strip()


def postpush_gate(repo: Path) -> dict[str, str]:
    branch = _git(repo, "branch", "--show-current")
    head = _git(repo, "rev-parse", "HEAD")
    origin = _git(repo, "rev-parse", "refs/remotes/origin/main")
    parent = _git(repo, "rev-parse", "HEAD^")
    changes = _git(repo, "diff-tree", "--no-commit-id", "--name-status", "-r", "HEAD")
    lines = [line.split("\t", 1) for line in changes.splitlines() if line]
    expected = set((repo / "docs/F4_2A_OVERLAY_FILELIST_v1.txt").read_text().splitlines())
    if (branch != "main" or head != origin or parent != PARENT
            or _git(repo, "status", "--porcelain", "--untracked-files=all")
            or len(expected) != 26 or len(lines) != 26
            or any(status != "A" for status, _ in lines)
            or {path for _, path in lines} != expected):
        raise RuntimeError("F4_2A_POSTPUSH_GATE_BLOCKED: exact 26-additions one-commit parent required")
    return {"branch": branch, "head": head, "origin_main": origin, "parent": parent}


def read_m1(popdir: Path) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    if any(token in str(popdir).upper() for token in ("MID_TEST", "CALIBRATION", "/TEST/")):
        raise ValueError("Forbidden TEST/CAL inputs")
    for filename, checksum in M1_FILES.items():
        path = popdir / filename
        if not path.is_file() or digest(path) != checksum:
            raise RuntimeError(f"F4_2A_M1_HASH_BLOCKED: {path}")
    household, person, resource = (pd.read_csv(popdir / p, low_memory=False)
                                    for p in M1_FILES)
    if (len(household), len(person), len(resource)) != (54828, 100000, 642364):
        raise ValueError("F4_2A_M1_CARDINALITY_BLOCKED")
    return household, person, resource


def make_context(households: pd.DataFrame, persons: pd.DataFrame,
                 resources: pd.DataFrame) -> Any:
    context = build_runtime_context(households, persons, resources,
        ScenarioDayContext(SCENARIO_ID, scenario_weekday=3, scenario_season=2))
    if (len(context.frame) != 100000 or context.frame["source_person_id"].duplicated().any()):
        raise ValueError("Full accepted M1 identity gate blocked")
    return context


def _df_bytes(frame: pd.DataFrame, path: Path) -> None:
    write_gzip_rows(path, tuple(frame.columns), frame.to_dict("records"))


def generate_full(repo: Path, context: Any, target: Path) -> dict[str, Any]:
    """Each call uses a newly loaded frozen selected generator, full 100k."""
    if target.exists():
        raise FileExistsError(f"Output path already exists: {target}")
    target.mkdir(parents=True)
    generated = ProductionDGenGenerator(repo).generate(context)
    if (len(generated.day_rows) != 100000 or generated.day_rows["row_id"].nunique() != 100000):
        raise RuntimeError("Full frozen M2 population realization missing")
    if generated.support_audit.get("unhandled_runtime_categories") != 0:
        raise RuntimeError("Unsupported full-M1 feature category; return MAIN")
    trip = generated.trip_rows
    day = generated.day_rows
    if any(c in trip.columns for c in ("chosen_mode", "selected_mode", "realized_route", "execution_outcome")):
        raise RuntimeError("NFI data leaked into frozen demand")
    if not set(trip["origin_activity"]).union(set(trip["destination_activity"])).issubset(
        {"HOME", "WORK", "EDUCATION", "BUSINESS", "SHOPPING", "LEISURE", "OTHER", "ESCORT"}
    ):
        raise ValueError("Taxonomy projection outside frozen 8-state vocabulary")
    _df_bytes(context.frame, target / "dgen_context_v1.csv.gz")
    _df_bytes(day, target / "dgen_day_rows_v1.csv.gz")
    _df_bytes(trip, target / "dgen_trip_rows_v1.csv.gz")
    generated.projection_audit.to_csv(target / "activity_taxonomy_projection_audit_v1.csv",
                                       index=False, lineterminator="\n")
    write_json(target / "support_audit_v1.json", generated.support_audit)
    write_json(target / "artifact_validation_v1.json", {"artifacts": list(generated.artifact_validation)})
    hashes = {path.name: digest(path) for path in sorted(target.iterdir()) if path.is_file()}
    return {"hashes": hashes, "days": len(day), "trips": len(trip),
            "unhandled_categories": generated.support_audit["unhandled_runtime_categories"]}


def adapt_full(day: pd.DataFrame, trip: pd.DataFrame) -> tuple[PersonDayPlan, ...]:
    """Chunk exact existing adapter; do not alter its frozen semantics."""
    sorted_days = day.sort_values(["replicate_index", "row_id"], kind="mergesort")
    plans: list[PersonDayPlan] = []
    # Avoid native adapter's quadratic full-day filtering, preserve exact code.
    for start in range(0, len(sorted_days), 500):
        selection = sorted_days.iloc[start:start + 500]
        ids = set(selection["row_id"].astype(str))
        relevant = trip.loc[trip["row_id"].astype(str).isin(ids)]
        plans.extend(adapt_joint_generated_frames(selection, relevant))
    if len(plans) != 100000 or len({p.person_id for p in plans}) != 100000:
        raise RuntimeError("100k M2 -> canonical M3 identity mismatch")
    return tuple(plans)


def check_day_support(plans: tuple[PersonDayPlan, ...], supply: FrozenSupply) -> dict[str, int | float]:
    no_trip, escort, escort_activities, total_trips, excluded_trips = 0, 0, 0, 0, 0
    for plan in plans:
        if plan.household_id not in supply.anchors:
            raise ValueError("Missing C home anchor for accepted M1 household")
        if plan.trips and plan.trips[0].origin_activity != "HOME":
            raise ValueError(f"MAIN_BLOCKER_INITIAL_NON_HOME: {plan.person_id}")
        if not plan.trips:
            no_trip += 1
        count = len(plan.trips)
        total_trips += count
        if any(t.origin_activity == "ESCORT" or t.destination_activity == "ESCORT"
               for t in plan.trips):
            escort += 1
            escort_activities += sum(a.activity == "ESCORT" for a in plan.activities)
            excluded_trips += count
        if not plan.temporal_chain_valid or not plan.distance_chain_valid:
            raise ValueError("Invalid frozen M2 temporal/distance chain")
    return {"all_day_plans": len(plans), "no_trip_days": no_trip,
            "escort_excluded_days": escort, "escort_excluded_trips": excluded_trips,
            "escort_activity_occurrences": escort_activities,
            "escort_day_share": escort / len(plans),
            "escort_person_share": escort / len(plans),
            "all_frozen_m2_trips": total_trips}


def _trip_rows(result: CoreSpatialized, policy: Policy,
               metric: Spatializer) -> tuple[list[dict[str, Any]], list[float], dict[str, Counter[str]]]:
    rows: list[dict[str, Any]] = []
    errors: list[float] = []
    visits: dict[str, Counter[str]] = {}
    for day in result.days:
        for item in day.trips:
            ox, oy = metric.metric(item.origin)
            dx, dy = metric.metric(item.destination)
            d = math.hypot(dx - ox, dy - oy) / 1000.0
            err = abs_log_ratio(d, item.demand.distance_prior_km)
            errors.append(err)
            if item.demand.destination_activity != "HOME":
                purpose = ("WORK_COMMUTE" if item.demand.destination_activity == "WORK"
                           else item.demand.destination_activity)
                visits.setdefault(purpose, Counter())[item.destination.location_id] += 1
            rows.append({"policy": policy, "row_id": day.base_plan.day_id,
                "person_id": day.base_plan.person_id, "trip_index": item.demand.trip_index,
                "origin_activity": item.demand.origin_activity,
                "destination_activity": item.demand.destination_activity,
                "origin_location_id": item.origin.location_id,
                "destination_location_id": item.destination.location_id,
                "euclidean_distance_km": d,
                "distance_prior_km": item.demand.distance_prior_km,
                "abs_log_ratio": "INF" if math.isinf(err) else err})
    return rows, errors, visits


def _concentration(visits: Counter[str], n_supply: int) -> dict[str, int | float]:
    n = sum(visits.values())
    occupied = len(visits)
    if n == 0:
        return {"unique_locations_used": 0, "normalized_hhi": 0.0, "top_1pct_share": 0.0}
    hhi = math.fsum((count / n) ** 2 for count in visits.values())
    hhi_norm = (hhi - 1 / n_supply) / (1 - 1 / n_supply) if n_supply > 1 else 1.0
    k = max(1, math.ceil(0.01 * n_supply))
    top = sum(sorted(visits.values(), reverse=True)[:k]) / n
    return {"unique_locations_used": occupied, "normalized_hhi": hhi_norm,
            "top_1pct_share": top}


def write_spatial_policy(root: Path, policy: Policy, result: CoreSpatialized,
                         spatializer: Spatializer, supply: FrozenSupply,
                         coverage: dict[str, int | float], seconds: float) -> dict[str, Any]:
    target = root / policy
    if target.exists():
        raise FileExistsError(target)
    target.mkdir(parents=True)
    trips, errors, visits = _trip_rows(result, policy, spatializer)
    dayrows = [{"policy": policy, "row_id": d.base_plan.day_id,
        "person_id": d.base_plan.person_id, "household_id": d.base_plan.household_id,
        "home_location_id": d.home_anchor.location.location_id,
        "trip_count": len(d.trips), "core_status": "INCLUDED_ONLY"} for d in result.days]
    stable_rows = [{"policy": policy, "person_id": a.person_id, "purpose": a.purpose,
        "location_id": a.location_id, "prior_aggregate_km": a.prior_aggregate_km}
        for a in result.stable_locations]
    write_gzip_rows(target / f"core_spatialized_trips_{policy}_v1.csv.gz",
                    ("policy", "row_id", "person_id", "trip_index", "origin_activity",
                     "destination_activity", "origin_location_id", "destination_location_id",
                     "euclidean_distance_km", "distance_prior_km", "abs_log_ratio"), trips)
    write_gzip_rows(target / f"core_spatialized_days_{policy}_v1.csv.gz",
                    ("policy", "row_id", "person_id", "household_id", "home_location_id",
                     "trip_count", "core_status"), dayrows)
    write_gzip_rows(target / f"core_stable_locations_{policy}_v1.csv.gz",
                    ("policy", "person_id", "purpose", "location_id", "prior_aggregate_km"), stable_rows)
    invariants = {"non_escort_coverage": len(result.days) == coverage["all_day_plans"] - coverage["escort_excluded_days"],
        "zero_home_mutations": all(d.home_anchor.location.location_id == supply.anchors[d.base_plan.household_id].location.location_id for d in result.days),
        "exact_trip_count": len(trips) == coverage["all_frozen_m2_trips"] - coverage["escort_excluded_trips"],
        "no_trip_home_only": all(not d.trips for d in result.days if not d.base_plan.trip_day),
        "no_escort_included": all(not any(t.demand.destination_activity == "ESCORT" or
               t.demand.origin_activity == "ESCORT" for t in d.trips) for d in result.days)}
    if not all(invariants.values()):
        raise RuntimeError(f"Hard F4.2a invariant failed: {invariants}")
    metrics: dict[str, Any] = {"policy": policy, "hard_invariants": invariants,
        "distance_error": extended_metrics(errors),
        "zero_distance_trip_count": sum(r["euclidean_distance_km"] == 0 for r in trips),
        "zero_distance_rate": sum(r["euclidean_distance_km"] == 0 for r in trips) / len(trips)
            if trips else 0.0,
        "coverage": {**coverage, "core_days": len(result.days), "core_trips": len(trips)},
        "concentration": {purpose: _concentration(counter, len(supply.indices[purpose].candidates))
                          for purpose, counter in sorted(visits.items())},
        "runtime_performance": {"wall_seconds": "REPORTED_SEPARATELY_NON_CANONICAL",
            "candidate_visits": result.index_candidate_visits},
        "candidate_role": "NON_SELECTABLE_ABLATION" if policy == "S_ATTR" else
                ("DIAGNOSTIC_BASELINE" if policy == "S_NEAR" else "CONDITIONAL_CORE_CANDIDATE")}
    write_json(target / f"core_metrics_{policy}_v1.json", metrics)
    return metrics


def _file_hashes(root: Path) -> dict[str, str]:
    return {p.relative_to(root).as_posix(): digest(p) for p in sorted(root.rglob("*")) if p.is_file()}


def run_official(repo: Path, population: Path, c_output: Path, output: Path) -> dict[str, Any]:
    git = postpush_gate(repo)
    if output.exists() or output.with_name(output.name + ".partial").exists():
        raise FileExistsError("Official output and staging paths must be unused")
    household, persons, resources = read_m1(population)
    frozen_input_gate(c_output)
    # Supply must be exact 88,879, anchors 54,828 and purpose evidence admissible.
    supply = load_frozen_supply(c_output)
    if not set(persons["household_id"].astype(str)).issubset(set(supply.anchors)):
        raise RuntimeError("Frozen C home anchors missing M1 household identifiers")
    context = make_context(household, persons, resources)
    partial = output.with_name(output.name + ".partial")
    partial.mkdir(parents=True)
    try:
        gen_a = generate_full(repo, context, partial / "dgen_A")
        gen_b = generate_full(repo, context, partial / "dgen_B")
        if gen_a["hashes"] != gen_b["hashes"]:
            raise RuntimeError("F4_2A_FULL_DGEN_TWO_RUN_SHA_MISMATCH")
        frozen = partial / "dgen_A"
        day = pd.read_csv(frozen / "dgen_day_rows_v1.csv.gz", low_memory=False)
        trip = pd.read_csv(frozen / "dgen_trip_rows_v1.csv.gz", low_memory=False)
        plans = adapt_full(day, trip)
        coverage = check_day_support(plans, supply)
        exclusions = []
        for p in plans:
            n = sum(a.activity == "ESCORT" for a in p.activities)
            if n:
                exclusions.append({"row_id": p.day_id, "person_id": p.person_id,
                    "reason": "ESCORT_DAY", "trip_count": len(p.trips), "escort_activity_count": n})
        write_gzip_rows(partial / "core_exclusions_v1.csv.gz",
                        ("row_id", "person_id", "reason", "trip_count", "escort_activity_count"),
                        exclusions)
        write_gzip_rows(partial / "core_person_days_v1.csv.gz",
            ("row_id", "person_id", "household_id", "core_status", "trip_count", "scenario_day_id"),
            ({"row_id": p.day_id, "person_id": p.person_id, "household_id": p.household_id,
             "core_status": "EXCLUDED_ESCORT" if any(t.origin_activity == "ESCORT" or t.destination_activity == "ESCORT" for t in p.trips) else "INCLUDED",
             "trip_count": len(p.trips), "scenario_day_id": SCENARIO_DAY_ID} for p in plans))
        metric_runs: list[dict[str, dict[str, Any]]] = []
        observed_performance: dict[str, dict[str, dict[str, float | int]]] = {}
        first_hashes: dict[str, str] | None = None
        for run_index in (1, 2):
            stage = partial / f"spatial_{run_index}"
            stage.mkdir()
            stage_metrics: dict[str, dict[str, Any]] = {}
            observed_performance[str(run_index)] = {}
            for policy in POLICIES:
                spatializer = Spatializer(supply.indices, supply.locations, supply.anchors)
                started = time.perf_counter()
                spatial = spatializer.spatialize(plans, policy)
                elapsed = time.perf_counter() - started
                stage_metrics[policy] = write_spatial_policy(stage, policy, spatial,
                                                              spatializer, supply, coverage, elapsed)
                observed_performance[str(run_index)][policy] = {
                    "wall_seconds": elapsed,
                    "candidate_visits": spatial.index_candidate_visits,
                    "peak_rss_kb": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
                }
            # All spatial outputs, including metrics JSON, must be bytewise equal.
            logical_hashes = _file_hashes(stage)
            if first_hashes is not None and first_hashes != logical_hashes:
                raise RuntimeError("F4_2A_SPATIAL_TWO_RUN_SHA_MISMATCH")
            first_hashes = logical_hashes
            metric_runs.append(stage_metrics)
        a = metric_runs[0]
        promotion = preregistered_promotion(a["S_NEAR"]["distance_error"],
                                            a["S_DIST"]["distance_error"])
        summary = {"status": "RETURN_TO_MAIN", "git": git,
            "scenario": {"id": SCENARIO_ID, "day_id": SCENARIO_DAY_ID,
                         "weekday": 3, "season": 2, "master_seed": 20261007,
                         "replicate_index": 0, "persons": 100000},
            "full_dgen_A_B_exact": True, "spatial_two_run_exact": True,
            "candidate_promotable_internal_only": promotion,
            "g3_opened": False, "cal_reads": 0, "mid_test_reads": 0,
            "m1_hashes": M1_FILES, "C_hashes": {name: digest(c_output / name)
                for name in ("location_supply_v1.csv.gz", "location_supply_evidence_v1.csv.gz",
                             "residential_anchors_v1.csv.gz", "residential_anchor_evidence_v1.csv.gz")},
            "coverage": coverage, "metrics": a,
            "noncanonical_performance_evidence": observed_performance,
            "environment": {"python": platform.python_version(),
                            "platform": platform.platform()}}
        write_json(partial / "run_manifest.json", summary)
        write_json(partial / "runbundle_sha256.json", _file_hashes(partial))
        partial.rename(output)
        return summary
    except BaseException:
        # Retain all partial evidence for MAIN, never overwrite and never promote.
        raise


def main() -> int:
    p = argparse.ArgumentParser(description="F4.2a post-push full-reference only")
    p.add_argument("--repo-root", type=Path, required=True)
    p.add_argument("--population-run-dir", type=Path, required=True)
    p.add_argument("--c-output-dir", type=Path, required=True)
    p.add_argument("--output-dir", type=Path, required=True)
    p.add_argument("--precheck-only", action="store_true")
    args = p.parse_args()
    repo = args.repo_root.resolve()
    if args.precheck_only:
        postpush_gate(repo)
        read_m1(args.population_run_dir)
        frozen_input_gate(args.c_output_dir)
        print("F4_2A_FULL_INPUT_POSTPUSH_PRECHECK=PASS")
        return 0
    summary = run_official(repo, args.population_run_dir, args.c_output_dir, args.output_dir)
    print(json.dumps({"status": summary["status"], "promotable":
                      summary["candidate_promotable_internal_only"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
