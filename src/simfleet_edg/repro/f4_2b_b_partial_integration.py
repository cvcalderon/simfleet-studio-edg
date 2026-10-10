"""F4.2b-B deterministic 11-scenario append-only ESCORT spatialization.

Requires the user's manual PyCharm commit/push first. No regeneration,
selection, CAL, MiD TEST, route, or co-travel inference.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import runpy
import subprocess
import tarfile
from collections import Counter
from pathlib import Path
from typing import Any

import yaml  # type: ignore[import-untyped]

from simfleet_edg.repro.f4_2a_core_spatial import M1_FILES
from simfleet_edg.repro.f4_2b_a_local_sensitivity import write_gzip_stream
from simfleet_edg.spatial.candidate_policies import extended_metrics
from simfleet_edg.spatial.escort_day_binding import (
    VARIANTS,
    by_day,
    frozen_anchors,
    read_csv_gz,
    read_proposals,
)
from simfleet_edg.spatial.escort_event_index import index_frozen_m2
from simfleet_edg.spatial.escort_partial_day_index import OriginalDay, load_original_days
from simfleet_edg.spatial.escort_partial_integration import (
    STATUS_RESOLVED,
    integrate_escort_day,
)
from simfleet_edg.spatial.escort_partial_ledger import (
    DAY_COLUMNS,
    DELTA_COLUMNS,
    TRIP_COLUMNS,
    day_rows,
    delta_rows,
    trip_rows,
)
from simfleet_edg.spatial.spatial_core_io import (
    digest,
    frozen_input_gate,
    load_frozen_supply,
    write_json,
)
from simfleet_edg.spatial.spatialize_core import Spatializer

PARENT = "1fdfd815fb5085cbc674b66baecd932a9bcabff9"
F4A_TAR = "9d97b2294e24d97709bc8ba4f103f94b5b21d2c4d64d7ed72efe35d24f816247"
B2A_TAR = "7aa0c4756f2bfca3e58988c4053083f52d4b1166621ba29ae6629cf7edc6bb3b"
SCIENCE_CLASS = "SYNTHETIC_HYPOTHETICAL_NOT_OBSERVED"
FORBIDDEN = ("MID_TEST", "MIDTH", "CALIBRATION", "/CAL/", "/TEST/")


def safe(path: Path) -> Path:
    out = path.expanduser().resolve()
    if any(x in str(out).upper() for x in FORBIDDEN):
        raise ValueError("BLOCKED_FORBIDDEN_SOURCE_OR_OUTPUT")
    return out


def _git(repo: Path, *args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=repo, text=True).strip()


def git_gate(repo: Path) -> dict[str, str]:
    """New commit HEAD is intentionally unknown until user manually pushes."""
    branch = _git(repo, "symbolic-ref", "--quiet", "--short", "HEAD")
    head = _git(repo, "rev-parse", "HEAD")
    origin = _git(repo, "rev-parse", "refs/remotes/origin/main")
    parent = _git(repo, "rev-parse", "HEAD^")
    lines = _git(repo, "diff-tree", "--no-commit-id", "--name-status",
                 "--no-renames", "-r", "HEAD").splitlines()
    changes = [line.split("\t", 1) for line in lines]
    paths = (repo / "docs/F4_2B_B_OVERLAY_FILELIST_v1.txt").read_text().splitlines()
    if (branch != "main" or head != origin or head == PARENT or parent != PARENT
            or _git(repo, "status", "--porcelain=v1", "--untracked-files=all")
            or len(paths) != 25 or len(set(paths)) != 25
            or len(changes) != 25 or set(map(tuple, changes)) != {
                ("A", path) for path in paths}):
        raise RuntimeError("BLOCKED_F4_2B_B_POSTPUSH_GIT_LINEAGE")
    # Freeze overlay checksums against both committed Git blobs and working tree.
    entries = (repo / "docs/F4_2B_B_OVERLAY_CHECKSUMS_v1.sha256").read_text().splitlines()
    found: set[str] = set()
    for line in entries:
        checksum, rel = line.split("  ", 1)
        if (rel in found or rel not in paths
                or digest(repo / rel) != checksum):
            raise RuntimeError("BLOCKED_F4_2B_B_NEW_OVERLAY_HASH")
        found.add(rel)
    if found != set(paths) - {"docs/F4_2B_B_OVERLAY_CHECKSUMS_v1.sha256"}:
        raise RuntimeError("BLOCKED_F4_2B_B_OVERLAY_MANIFEST_INCOMPLETE")
    # Reuse the frozen-overlay + 19-key audits from the same committed 25-file overlay.
    checks = runpy.run_path(str(repo / "scripts/verify_f4_2b_b_preopen.py"))
    checks["verify_prior_overlays"](repo)
    checks["verify_protected"](repo)
    return {"branch": branch, "head": head, "origin_main": origin, "parent": parent}


def verify_original_tar_tree(archive: Path, extracted: Path) -> int:
    """Bind every read-only extracted byte to its exact immutable TAR member.

    Reject links, traversal, missing members, extra files and modified extracted
    payloads. Never extract archives into the repository or create new inputs.
    """
    with tarfile.open(archive, mode="r:gz") as source:
        members = [item for item in source.getmembers() if item.isfile()]
        if not members or any(item.issym() or item.islnk() for item in source.getmembers()):
            raise RuntimeError("BLOCKED_ORIGINAL_TAR_FILE_TYPES")
        parts = []
        for member in members:
            name = member.name.lstrip("./")
            raw = Path(name)
            if (not name or raw.is_absolute() or ".." in raw.parts
                    or not raw.parts):
                raise RuntimeError("BLOCKED_ORIGINAL_TAR_PATH")
            parts.append(raw.parts)
        strip = (len(parts[0]) > 1 and all(p[0] == parts[0][0] for p in parts))
        names: set[str] = set()
        for member, parsed in zip(members, parts, strict=True):
            rel = Path(*parsed[1:]) if strip else Path(*parsed)
            if not rel.parts or rel.as_posix() in names:
                raise RuntimeError("BLOCKED_ORIGINAL_TAR_DUPLICATE_MEMBER")
            names.add(rel.as_posix())
            artifact = extracted / rel
            if not artifact.is_file():
                raise RuntimeError("BLOCKED_ORIGINAL_TAR_MISSING_EXTRACTED: " + str(rel))
            stream = source.extractfile(member)
            if stream is None:
                raise RuntimeError("BLOCKED_ORIGINAL_TAR_MEMBER_READ")
            h = hashlib.sha256()
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                h.update(chunk)
            if digest(artifact) != h.hexdigest():
                raise RuntimeError("BLOCKED_ORIGINAL_TAR_EXTRACTED_BYTES_MISMATCH: " + str(rel))
    present = {p.relative_to(extracted).as_posix() for p in extracted.rglob("*") if p.is_file()}
    if present != names:
        raise RuntimeError("BLOCKED_ORIGINAL_TAR_EXTRA_EXTRACTED_FILES")
    return len(names)


def _hash_manifest(root: Path, name: str) -> dict[str, str]:
    expected: dict[str, str] = json.loads((root / name).read_text())
    for rel, checksum in expected.items():
        if not isinstance(rel, str) or Path(rel).is_absolute() or ".." in Path(rel).parts:
            raise RuntimeError("BLOCKED_UPSTREAM_MANIFEST_PATH")
        if not (root / rel).is_file() or digest(root / rel) != checksum:
            raise RuntimeError("BLOCKED_UPSTREAM_ARTIFACT_HASH: " + rel)
    return expected


def _b2_a_pairwise(b2: Path) -> dict[str, str]:
    a = {p.name: digest(p) for p in (b2 / "A").iterdir() if p.is_file()}
    b = {p.name: digest(p) for p in (b2 / "B").iterdir() if p.is_file()}
    manifest = json.loads((b2 / "runbundle_manifest_v1.json").read_text())
    if a != b or a != manifest["sha256_by_relative_path"] or len(a) != 25:
        raise RuntimeError("BLOCKED_F4_2B_A_PAIRWISE_HASH")
    return a


def input_gate(f4a_tar: Path, b2a_tar: Path, f4a: Path, b2a: Path,
               population: Path, c_output: Path) -> dict[str, Any]:
    """Verify originals and exact extracted bytes; do not reconstruct or redraw."""
    if digest(f4a_tar) != F4A_TAR or digest(b2a_tar) != B2A_TAR:
        raise RuntimeError("BLOCKED_FROZEN_TAR_SHA")
    f4_members = verify_original_tar_tree(f4a_tar, f4a)
    b2_members = verify_original_tar_tree(b2a_tar, b2a)
    f4hashes = _hash_manifest(f4a, "runbundle_sha256.json")
    b2hashes = _hash_manifest(b2a, "runbundle_all_checksums_v1.json")
    _b2_a_pairwise(b2a)
    # A/B DGEN and S_DIST frozen equality, with no regeneration.
    for part in ("dgen_day_rows_v1.csv.gz", "dgen_trip_rows_v1.csv.gz",
                 "dgen_context_v1.csv.gz"):
        if digest(f4a / "dgen_A" / part) != digest(f4a / "dgen_B" / part):
            raise RuntimeError("BLOCKED_F4A_DGEN_A_B")
    for suffix in ("days", "trips", "stable_locations"):
        filename = f"core_spatialized_{suffix}_S_DIST_v1.csv.gz" if suffix != "stable_locations" else (
            "core_stable_locations_S_DIST_v1.csv.gz")
        if digest(f4a / "spatial_1/S_DIST" / filename) != digest(
                f4a / "spatial_2/S_DIST" / filename):
            raise RuntimeError("BLOCKED_F4A_SPATIAL_A_B")
    for name, sha in M1_FILES.items():
        if digest(population / name) != sha:
            raise RuntimeError("BLOCKED_FROZEN_M1_HASH")
    frozen_input_gate(c_output)
    return {"f4a_tar": F4A_TAR, "b2a_tar": B2A_TAR,
            "f4a_internal_files": len(f4hashes), "b2a_internal_files": len(b2hashes),
            "verified_f4a_tar_members": f4_members, "verified_b2a_tar_members": b2_members,
            "m1": M1_FILES}


def core_trip_references(f4a: Path, days: tuple[OriginalDay, ...], *, strict: bool = True
                        ) -> dict[tuple[str, int], tuple[str, str]]:
    rows = read_csv_gz(f4a / "spatial_1/S_DIST/core_spatialized_trips_S_DIST_v1.csv.gz")
    lookup: dict[tuple[str, int], tuple[str, str]] = {}
    for r in rows:
        if r["policy"] != "S_DIST":
            raise ValueError("BLOCKED_CORE_POLICY")
        key = (r["row_id"], int(r["trip_index"]))
        if key in lookup or not r["origin_location_id"] or not r["destination_location_id"]:
            raise ValueError("BLOCKED_CORE_LOCATION_REF")
        lookup[key] = (r["origin_location_id"], r["destination_location_id"])
    required = {(day.row_id, t.trip_index) for day in days if not day.has_escort
                for t in day.trips}
    if set(lookup) != required or (strict and len(lookup) != 240751):
        raise ValueError("BLOCKED_CORE_EXACT_TRIP_SET")
    return lookup


def _counts(days: tuple[OriginalDay, ...]) -> dict[str, int]:
    core_days = sum(not d.has_escort for d in days)
    escort_days = len(days) - core_days
    return {"all_days": len(days), "all_trips": sum(len(d.trips) for d in days),
            "core_days": core_days, "escort_days": escort_days,
            "core_trips": sum(len(d.trips) for d in days if not d.has_escort),
            "escort_trips": sum(len(d.trips) for d in days if d.has_escort),
            "escort_events": sum(t.destination_activity == "ESCORT" for d in days
                                 for t in d.trips)}


def _summary(variant: str, days: tuple[OriginalDay, ...], resolutions: dict[str, Any],
             event_statuses: Counter[str], candidate_visits: int) -> dict[str, Any]:
    statuses = Counter(r.status for r in resolutions.values())
    errors = [t.abs_log_ratio for r in resolutions.values() if r.status == STATUS_RESOLVED
              for t in r.trips]
    zero = sum(t.euclidean_distance_km == 0 for r in resolutions.values()
               if r.status == STATUS_RESOLVED for t in r.trips)
    failure_reasons: Counter[str] = Counter()
    for item in resolutions.values():
        failure_reasons.update(item.reasons)
    spatialized = statuses[STATUS_RESOLVED]
    spatial_trips = sum(len(r.trips) for r in resolutions.values() if r.status == STATUS_RESOLVED)
    denominators = _counts(days)
    return {"variant_id": variant, "science_class": SCIENCE_CLASS,
            "status": "RETURN_TO_MAIN_NO_SELECTION_NO_G3",
            "denominators": denominators, "coverage_and_failures": {
                "link_complete_days": sum(r.links_complete for r in resolutions.values()),
                "spatialized_escort_days": spatialized,
                "spatialized_escort_trips": spatial_trips,
                "unresolved_escort_days": denominators["escort_days"] - spatialized,
                "unresolved_escort_trips": denominators["escort_trips"] - spatial_trips,
                "integrated_day_count_including_core": denominators["core_days"] + spatialized,
                "integrated_trip_count_including_core": denominators["core_trips"] + spatial_trips,
                "day_states": dict(sorted(statuses.items())),
                "event_states": dict(sorted(event_statuses.items())),
                "typed_reasons": dict(sorted(failure_reasons.items())),
                "escort_day_coverage_fraction": spatialized / denominators["escort_days"],
                "escort_trip_coverage_fraction": spatial_trips / denominators["escort_trips"]},
            "technical_diagnostics_only": {
                "distance_error": extended_metrics(errors) if errors else None,
                "zero_distance_trips": zero,
                "zero_distance_rate": zero / spatial_trips if spatial_trips else 0.0,
                "candidate_visits": candidate_visits},
            "policy": "S_DIST", "core_preservation": "REFERENCE_ONLY_BY_IMMUTABLE_SHA",
            "real_person_linkage_observed": False, "co_travel_observed": False,
            "experimental_variant_selected": False, "pHH_causal_isolation": False,
            "f4_2c_open": False, "g3_open": False, "cal_reads": 0, "mid_test_reads": 0}


def run_one_variant(variant: str, days: tuple[OriginalDay, ...], b2a: Path,
                    anchors: dict[tuple[str, str], Any], idx: Any, supply: Any,
                    core_refs: dict[tuple[str, int], tuple[str, str]], output: Path,
                    *, strict: bool = True) -> dict[str, Any]:
    if output.exists():
        raise FileExistsError(output)
    proposals = read_proposals(b2a / "A" / f"escort_location_proposals_{variant}_v1.csv.gz",
                               days, variant, idx.person_households, idx.activities,
                               anchors, frozenset(supply.locations), strict=strict)
    grouped = by_day(proposals)
    resolutions = {}
    visits = 0
    spatial = Spatializer(supply.indices, supply.locations, supply.anchors)
    for day in days:
        if not day.has_escort:
            continue
        events = {r["event_id"]: r for r in grouped.get(day.row_id, ())}
        answer = integrate_escort_day(day, events, anchors, spatial)
        resolutions[day.row_id] = answer
        visits += spatial._visited
    if len(resolutions) != (15381 if strict else sum(d.has_escort for d in days)):
        raise RuntimeError("BLOCKED_VARIANT_WHOLE_DAY_COUNT")
    summary = _summary(variant, days, resolutions,
                       Counter(r["status"] for r in proposals.values()), visits)
    linked_scope = Counter(r["scope"] for r in proposals.values()
                           if r["status"] == "RESOLVED_LOCATION_ONLY")
    linked_purposes = Counter(r["target_purpose"] for r in proposals.values()
                              if r["status"] == "RESOLVED_LOCATION_ONLY")
    summary["coverage_and_failures"]["inherited_scope_counts"] = dict(sorted(linked_scope.items()))
    summary["coverage_and_failures"]["inherited_purpose_counts"] = dict(sorted(linked_purposes.items()))
    frozen = yaml.safe_load((Path(__file__).resolve().parents[3] /
                            "configs/f4/f4_2b_b_partial_integration_preopen_v1.yaml").read_text())
    upper = frozen["frozen_upper_bounds"][variant]
    complete_rows = {rid for rid, result in resolutions.items() if result.links_complete}
    complete_trips = sum(len(d.trips) for d in days if d.row_id in complete_rows)
    if complete_trips != upper["link_complete_trips"]:
        raise RuntimeError("BLOCKED_MAIN_LINK_COMPLETE_TRIP_UPPER_BOUND")
    if (summary["coverage_and_failures"]["link_complete_days"] != upper["link_complete_days"]
            or summary["coverage_and_failures"]["event_states"].get("RESOLVED_LOCATION_ONLY", 0)
            != upper["resolved_escort_events"]):
        raise RuntimeError("BLOCKED_MAIN_LINK_COMPLETE_UPPER_BOUNDS")
    # No PENDING or fatal day in release. All 18,871 original events are referenced
    # from the immutable B2-A RunBundle and never filtered/regenerated.
    output.mkdir(parents=True)
    write_gzip_stream(output / "day_ledger_v1.csv.gz", DAY_COLUMNS,
                      day_rows(days, resolutions, variant))
    write_gzip_stream(output / "trip_ledger_v1.csv.gz", TRIP_COLUMNS,
                      trip_rows(days, resolutions, variant, core_refs))
    write_gzip_stream(output / "escort_spatialized_trip_delta_v1.csv.gz", DELTA_COLUMNS,
                      delta_rows(days, resolutions, variant))
    write_json(output / "variant_scientific_summary_v1.json", summary)
    return summary


def hashes(root: Path) -> dict[str, str]:
    return {p.relative_to(root).as_posix(): digest(p) for p in sorted(root.rglob("*"))
            if p.is_file()}


def run_full(repo: Path, pop: Path, c_out: Path, f4a_tar: Path, b2a_tar: Path,
             f4a: Path, b2a: Path, output: Path, *, mode: str) -> dict[str, Any]:
    git = git_gate(repo)
    source = input_gate(f4a_tar, b2a_tar, f4a, b2a, pop, c_out)
    if mode == "precheck":
        return {"status": "PRECHECK_PASS", "git": git, "inputs": source}
    if output.exists() or output.with_name(output.name + ".partial").exists():
        raise FileExistsError("BLOCKED_NO_OUTPUT_OVERWRITE")
    days = load_original_days(f4a)
    original_counts = _counts(days)
    if original_counts != {"all_days": 100000, "all_trips": 325613,
                           "core_days": 84619, "escort_days": 15381,
                           "core_trips": 240751, "escort_trips": 84862,
                           "escort_events": 18871}:
        raise RuntimeError("BLOCKED_FROZEN_TOTALS")
    idx = index_frozen_m2(f4a / "dgen_A/dgen_day_rows_v1.csv.gz",
                          f4a / "dgen_A/dgen_trip_rows_v1.csv.gz")
    if {d.person_id: d.household_id for d in days} != idx.person_households:
        raise RuntimeError("BLOCKED_FROZEN_M1_IDENTITY")
    with (pop / "M_P_CONSTR_RMIN_V2_HD_U_persons.csv").open(
            encoding="utf-8", newline="") as m1_handle:
        m1 = {r["person_id"]: r["household_id"] for r in csv.DictReader(m1_handle)}
    if len(m1) != 100000 or m1 != idx.person_households:
        raise RuntimeError("BLOCKED_ACCEPTED_M1_IDENTITY_MISMATCH")
    originals = read_csv_gz(f4a / "core_person_days_v1.csv.gz")
    if len(originals) != 100000:
        raise RuntimeError("BLOCKED_CORE_PERSON_DAYS_COUNT")
    original_statuses = {r["row_id"]: r["core_status"] for r in originals}
    if len(original_statuses) != 100000 or any(original_statuses.get(d.row_id) != (
            "EXCLUDED_ESCORT" if d.has_escort else "INCLUDED") for d in days):
        raise RuntimeError("BLOCKED_CORE_EXCLUSION_IDENTITY")
    supply = load_frozen_supply(c_out)
    if not set(idx.person_households.values()).issubset(supply.anchors):
        raise RuntimeError("BLOCKED_C_HOME_COVERAGE")
    assignments = frozen_anchors(f4a, b2a)
    required = {(d.person_id, "WORK_COMMUTE" if t.destination_activity == "WORK"
                 else "EDUCATION") for d in days if d.has_escort for t in d.trips
                if t.destination_activity in ("WORK", "EDUCATION")}
    if len(required) != 7621 or not required.issubset(assignments):
        raise RuntimeError("BLOCKED_REQUIRED_STABLE_7621_COVERAGE")
    if any(a.location_id not in supply.locations for a in assignments.values()):
        raise RuntimeError("BLOCKED_STABLE_LOCATION_NOT_IN_C")
    core = core_trip_references(f4a, days)
    staging = output.with_name(output.name + ".partial")
    staging.mkdir(parents=True)
    results: dict[str, Any] = {}
    if mode == "single":
        for variant in VARIANTS:
            results[variant] = run_one_variant(variant, days, b2a, assignments, idx,
                                               supply, core, staging / variant)
        write_json(staging / "run_manifest_v1.json", {
            "git_and_input_hashes": {"git": git, **source},
            "science_class": SCIENCE_CLASS, "variant_ids": list(VARIANTS),
            "summary": results, "core_reference": "F4.2a spatial_1/S_DIST immutable",
            "b2_a_proposals": "A originals, checked identical to B",
            "full_population_accounts": original_counts, "no_selection": True,
            "g3_opened": False, "f4_2c_opened": False})
        os.replace(staging, output)
        return {"status": "SINGLE_11_COMPLETE", "variants": len(results)}
    for independent in ("A", "B"):
        target = staging / independent
        target.mkdir()
        for variant in VARIANTS:
            results[variant] = run_one_variant(variant, days, b2a, assignments, idx,
                                               supply, core, target / variant)
    a, b = hashes(staging / "A"), hashes(staging / "B")
    if len(a) != 44 or a != b:
        raise RuntimeError("BLOCKED_F4_2B_B_AB_REPRODUCTION")
    write_json(staging / "run_manifest_v1.json", {
        "status": "RETURN_TO_MAIN_NO_G3", "science_class": SCIENCE_CLASS,
        "git_and_input_hashes": {"git": git, **source}, "variant_ids": list(VARIANTS),
        "sha256_canonical_by_relative_path": a, "two_independent_runs_byte_exact": True,
        "summary": results, "full_population_accounts": original_counts,
        "core_reference": "F4.2a spatial_1/S_DIST immutable",
        "b2_a_proposals": "A originals, checked identical to B", "no_selection": True,
        "g3_opened": False, "f4_2c_opened": False, "cal_reads": 0, "mid_test_reads": 0})
    write_json(staging / "runbundle_sha256_v1.json", hashes(staging))
    os.replace(staging, output)
    return {"status": "RETURN_TO_MAIN_NO_G3", "variants": len(results),
            "canonical_file_count_per_run": len(a), "a_b_exact": True}


def main() -> None:
    parser = argparse.ArgumentParser()
    for name in ("repo", "population", "c-output", "f4a-tar", "b2a-tar",
                 "f4a-dir", "b2a-dir", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--stage", choices=("precheck", "single", "full"), default="full")
    args = parser.parse_args()
    options = [safe(getattr(args, name)) for name in (
        "repo", "population", "c_output", "f4a_tar", "b2a_tar", "f4a_dir", "b2a_dir", "output")]
    print(json.dumps(run_full(*options, mode=args.stage), sort_keys=True))


if __name__ == "__main__":
    main()
