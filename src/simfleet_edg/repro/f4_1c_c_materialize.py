from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import importlib.metadata
import importlib.util
import json
import os
import platform
import shutil
import subprocess
import sys
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

import yaml  # type: ignore[import-untyped]

from simfleet_edg.spatial.location_supply import (
    CsvRow,
    LocationSupplyMaterialization,
    location_supply_row,
    materialize_location_supply,
)
from simfleet_edg.spatial.lor_lookup import EXPECTED_M1_BEZIRK_IDS, FrozenLorLookup
from simfleet_edg.spatial.osm_registry import EligibilityRegistry
from simfleet_edg.spatial.osm_source import md5_file, sha256_file
from simfleet_edg.spatial.residential_anchor import (
    HouseholdHomeInput,
    ResidentialAnchorRealization,
    realize_residential_anchors,
    residential_anchor_row,
)

EXPECTED_PHASE = "F4.1c-C"
EXPECTED_PARENT = "0958a673f0527b5bc87c16cb041e620f085ead87"
EXPECTED_SNAPSHOT = "OSM_GEOFABRIK_BERLIN_2026-10-04_V1"
OUTPUT_FILES = (
    "location_supply_v1.csv.gz",
    "location_supply_evidence_v1.csv.gz",
    "residential_supply_candidates_v1.csv.gz",
    "residential_anchors_v1.csv.gz",
    "residential_anchor_evidence_v1.csv.gz",
    "materialization_exclusions_v1.csv.gz",
)

LOCATION_SUPPLY_FIELDS = (
    "location_id",
    "level",
    "lon",
    "lat",
    "crs",
    "eligible_purposes_json",
    "attractiveness",
    "capacity",
    "provenance",
)
LOCATION_EVIDENCE_FIELDS = (
    "location_id",
    "source_snapshot_id",
    "osm_element_type",
    "osm_element_id",
    "supply_classes_json",
    "supply_tier",
    "a3_rule_ids_json",
    "matched_tags_json",
    "geometry_kind",
    "representative_point_method",
    "projected_area_m2",
    "osm_capacity_raw",
    "building_levels_raw",
    "plr_id",
    "lor_bzr_id",
    "pgr_id",
    "potential_duplicate_group_ids_json",
    "duplicate_policy",
    "provenance",
)
RESIDENTIAL_CANDIDATE_FIELDS = (
    "candidate_id",
    "source_snapshot_id",
    "osm_element_type",
    "osm_element_id",
    "supply_class",
    "parent_m1_bezirk_id",
    "parent_bezirk_code_2d",
    "source_area_m2",
    "allocation_area_m2",
    "pool_priority",
    "provenance",
)
RESIDENTIAL_ANCHOR_FIELDS = (
    "household_id",
    "location_id",
    "level",
    "lon",
    "lat",
    "crs",
    "parent_bezirk_id",
    "provenance",
)
RESIDENTIAL_ANCHOR_EVIDENCE_FIELDS = (
    "household_id",
    "source_candidate_id",
    "source_snapshot_id",
    "osm_element_type",
    "osm_element_id",
    "supply_class",
    "pool_class_used",
    "candidate_count_in_pool",
    "pool_total_mass_m2",
    "candidate_allocation_mass_m2",
    "selection_namespace",
    "selection_hash_sha256",
    "point_method",
    "point_attempt_index",
    "parent_bezirk_code_2d",
    "realized_plr_id",
    "realized_lor_bzr_id",
    "realized_pgr_id",
    "provenance",
)
EXCLUSION_FIELDS = (
    "osm_element_type",
    "osm_element_id",
    "reason",
    "detail_json",
    "provenance",
)


def _load_yaml(path: Path) -> dict[str, Any]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected YAML mapping: {path}")
    return cast(dict[str, Any], payload)


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _git(repo_root: Path, *args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=repo_root, text=True).strip()


def _environment() -> dict[str, Any]:
    packages = ("osmium", "shapely", "pyproj", "PyYAML")
    versions: dict[str, str | None] = {}
    for package in packages:
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


def _file_hash_ok(path: Path, expected: str) -> bool:
    return path.is_file() and sha256_file(path) == expected


def _contract_hash_ok(path: Path, expected: str) -> bool:
    if not path.is_file():
        return False
    if sha256_file(path) == expected:
        return True
    if path.suffix.lower() != ".csv":
        return False

    # F4.1c repository-entry audit documents CSV contract hashes that were
    # captured from csv.writer CRLF bytes before Git's `*.csv text eol=lf`
    # normalization. Canonicalize only EOL bytes back to CRLF; all other
    # content remains byte-exact and any scientific/content drift still fails.
    data = path.read_bytes()
    logical_lf = data.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    canonical_crlf = logical_lf.replace(b"\n", b"\r\n")
    return hashlib.sha256(canonical_crlf).hexdigest() == expected


def _count_csv_rows(path: Path) -> int:
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.reader(handle)
        next(reader, None)
        return sum(1 for _ in reader)


def precheck(
    repo_root: Path,
    config_path: Path,
    population_run_dir: Path,
    *,
    check_environment: bool = True,
    check_large_inputs: bool = True,
) -> dict[str, Any]:
    cfg = _load_yaml(config_path)
    checks: dict[str, bool] = {}
    checks["phase_exact"] = cfg.get("phase_id") == EXPECTED_PHASE
    checks["required_parent_exact"] = cfg.get("required_parent_commit") == EXPECTED_PARENT

    source = cast(dict[str, Any], cfg["source"])
    checks["snapshot_exact"] = source.get("source_snapshot_id") == EXPECTED_SNAPSHOT
    raw_path = repo_root / str(source["raw_path"])
    if check_large_inputs:
        checks["osm_exists"] = raw_path.is_file()
        if raw_path.is_file():
            checks["osm_size"] = raw_path.stat().st_size == int(source["size_bytes"])
            checks["osm_sha256"] = sha256_file(raw_path) == str(source["sha256"])
            checks["osm_md5"] = md5_file(raw_path) == str(source["provider_md5"])
        else:
            checks["osm_size"] = False
            checks["osm_sha256"] = False
            checks["osm_md5"] = False
    else:
        checks["osm_identity"] = True

    lor = cast(dict[str, Any], cfg["frozen_lor"])
    for level in ("plr", "bzr", "pgr"):
        spec = cast(dict[str, Any], lor[level])
        target = repo_root / str(spec["path"])
        checks[f"lor_hash:{level}"] = (
            _file_hash_ok(target, str(spec["sha256"])) if check_large_inputs else True
        )

    population = cast(dict[str, Any], cfg["population"])
    households = population_run_dir / str(population["households_filename"])
    persons = population_run_dir / str(population["persons_filename"])
    if check_large_inputs:
        checks["households_hash"] = _file_hash_ok(households, str(population["households_sha256"]))
        checks["persons_hash"] = _file_hash_ok(persons, str(population["persons_sha256"]))
        checks["households_count"] = households.is_file() and _count_csv_rows(households) == int(
            population["households"]
        )
        checks["persons_count"] = persons.is_file() and _count_csv_rows(persons) == int(
            population["persons"]
        )
    else:
        checks["population_identity"] = True

    contracts = cast(dict[str, str], cfg["frozen_contracts"])
    contract_hashes = cast(dict[str, str], cfg["frozen_contract_sha256"])
    for name, relative in contracts.items():
        checks[f"contract_hash:{name}"] = _contract_hash_ok(
            repo_root / relative,
            contract_hashes[name],
        )

    boundary = cast(dict[str, Any], cfg["execution_boundary"])
    checks["network_forbidden"] = boundary.get("network_access") == "FORBIDDEN"
    checks["destination_assignment_forbidden"] = (
        boundary.get("nonhome_destination_assignment") == "FORBIDDEN"
    )
    checks["s_near_closed"] = boundary.get("s_near") == "FORBIDDEN"
    checks["s_dist_closed"] = boundary.get("s_dist") == "FORBIDDEN"
    checks["s_attr_closed"] = boundary.get("s_attr") == "FORBIDDEN"
    checks["g3_closed"] = boundary.get("g3") == "NOT_OPEN"
    checks["mid_test_forbidden"] = boundary.get("mid_test") == "FORBIDDEN"

    if check_environment:
        checks["python_3_12"] = sys.version_info[:2] == (3, 12)
        checks["osmium_importable"] = importlib.util.find_spec("osmium") is not None
        checks["shapely_importable"] = importlib.util.find_spec("shapely") is not None
        checks["pyproj_importable"] = importlib.util.find_spec("pyproj") is not None
    else:
        checks["environment"] = True

    failed = sorted(name for name, passed in checks.items() if not passed)
    return {
        "phase": EXPECTED_PHASE,
        "mode": "PRECHECK",
        "status": "PASS" if not failed else "FAIL",
        "checks": checks,
        "failed": failed,
        "environment": _environment(),
        "network_access": "NONE",
    }


def require_frozen_implementation_commit(repo_root: Path) -> str:
    if not (repo_root / ".git").exists():
        raise RuntimeError("Official F4.1c-C execution requires a real Git clone")
    branch = _git(repo_root, "branch", "--show-current")
    head = _git(repo_root, "rev-parse", "HEAD")
    origin = _git(repo_root, "rev-parse", "origin/main")
    status = _git(repo_root, "status", "--porcelain", "--untracked-files=all")
    if branch != "main":
        raise RuntimeError("Official F4.1c-C execution requires branch main")
    if status:
        raise RuntimeError("Official F4.1c-C execution requires a clean worktree")
    if head != origin:
        raise RuntimeError("Official F4.1c-C execution requires HEAD == origin/main")
    if head == EXPECTED_PARENT:
        raise RuntimeError("Official F4.1c-C execution requires the C implementation commit")
    return head


def _read_population_inputs(
    population_run_dir: Path,
    population: dict[str, Any],
) -> tuple[tuple[HouseholdHomeInput, ...], tuple[str, ...]]:
    household_path = population_run_dir / str(population["households_filename"])
    person_path = population_run_dir / str(population["persons_filename"])

    households: list[HouseholdHomeInput] = []
    with household_path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        required = {"household_id", "home_zone_level", "home_zone_id"}
        if reader.fieldnames is None or not required.issubset(reader.fieldnames):
            raise ValueError("Accepted M1 household file lacks required HOME columns")
        for raw in reader:
            households.append(
                HouseholdHomeInput(
                    household_id=str(raw["household_id"]),
                    home_zone_level=str(raw["home_zone_level"]),
                    home_zone_id=str(raw["home_zone_id"]),
                )
            )

    person_households: list[str] = []
    with person_path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None or "household_id" not in reader.fieldnames:
            raise ValueError("Accepted M1 person file lacks household_id")
        for raw in reader:
            person_households.append(str(raw["household_id"]))
    return tuple(households), tuple(person_households)


def _load_lor(repo_root: Path, cfg: dict[str, Any]) -> FrozenLorLookup:
    lor = cast(dict[str, Any], cfg["frozen_lor"])
    plr = cast(dict[str, Any], lor["plr"])
    bzr = cast(dict[str, Any], lor["bzr"])
    pgr = cast(dict[str, Any], lor["pgr"])
    return FrozenLorLookup.from_geojson(
        plr_path=repo_root / str(plr["path"]),
        bzr_path=repo_root / str(bzr["path"]),
        pgr_path=repo_root / str(pgr["path"]),
        enforce_frozen_counts=True,
    )


def _materialize_in_memory(
    repo_root: Path,
    cfg: dict[str, Any],
    population_run_dir: Path,
) -> tuple[LocationSupplyMaterialization, ResidentialAnchorRealization, tuple[str, ...]]:
    contracts = cast(dict[str, str], cfg["frozen_contracts"])
    a3_policy = _load_yaml(repo_root / contracts["a3_policy"])
    extraction_keys = tuple(cast(list[str], a3_policy["extraction_key_universe_v1"]))
    registry = EligibilityRegistry.from_csv(repo_root / contracts["a3_registry"])
    lor_lookup = _load_lor(repo_root, cfg)
    source = cast(dict[str, Any], cfg["source"])

    supply = materialize_location_supply(
        source_path=repo_root / str(source["raw_path"]),
        registry=registry,
        extraction_keys=extraction_keys,
        lor_lookup=lor_lookup,
        source_snapshot_id=str(source["source_snapshot_id"]),
    )
    expected_purpose_counts = {
        str(key): int(value)
        for key, value in cast(dict[str, Any], cfg["inside_berlin_purpose_label_counts"]).items()
    }
    if supply.purpose_label_counts() != dict(sorted(expected_purpose_counts.items())):
        raise ValueError(
            "Operational purpose-label counts differ from the frozen B MAIN anchors: "
            f"{supply.purpose_label_counts()}"
        )

    candidate_boroughs = {
        row.parent_m1_bezirk_id
        for row in supply.residential_candidates
        if row.supply_class == "RESIDENTIAL_BUILDING"
    }
    if candidate_boroughs != set(EXPECTED_M1_BEZIRK_IDS):
        raise ValueError("Frozen source does not provide residential building support in all 12 boroughs")

    population = cast(dict[str, Any], cfg["population"])
    households, person_households = _read_population_inputs(population_run_dir, population)
    realization = realize_residential_anchors(
        households=households,
        candidates=supply.residential_candidates,
        lor_lookup=lor_lookup,
        source_snapshot_id=str(source["source_snapshot_id"]),
        require_all_frozen_boroughs=True,
    )
    if len(realization.anchors) != int(population["households"]):
        raise ValueError("Residential anchor cardinality differs from accepted M1 households")
    if realization.fallback_household_count != 0:
        raise ValueError("Frozen source unexpectedly used residential landuse fallback")

    anchor_households = {anchor.household_id for anchor in realization.anchors}
    if len(person_households) != int(population["persons"]):
        raise ValueError("Accepted M1 person cardinality mismatch")
    if not all(household_id in anchor_households for household_id in person_households):
        raise ValueError("At least one accepted M1 person does not reuse a household HOME anchor")

    return supply, realization, person_households


def _write_csv_gz(path: Path, fieldnames: tuple[str, ...], rows: Iterable[CsvRow]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as raw:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as compressed:
            with open_text_writer(compressed) as text:
                writer = csv.DictWriter(
                    text,
                    fieldnames=list(fieldnames),
                    extrasaction="raise",
                    lineterminator="\n",
                )
                writer.writeheader()
                writer.writerows(rows)


def open_text_writer(binary: Any) -> Any:
    import io

    return io.TextIOWrapper(binary, encoding="utf-8", newline="", write_through=True)


def _write_outputs(
    output_dir: Path,
    supply: LocationSupplyMaterialization,
    realization: ResidentialAnchorRealization,
) -> None:
    _write_csv_gz(
        output_dir / "location_supply_v1.csv.gz",
        LOCATION_SUPPLY_FIELDS,
        (location_supply_row(row) for row in supply.records),
    )
    _write_csv_gz(
        output_dir / "location_supply_evidence_v1.csv.gz",
        LOCATION_EVIDENCE_FIELDS,
        (row.to_row() for row in supply.evidence),
    )
    _write_csv_gz(
        output_dir / "residential_supply_candidates_v1.csv.gz",
        RESIDENTIAL_CANDIDATE_FIELDS,
        (row.to_row() for row in supply.residential_candidates),
    )
    _write_csv_gz(
        output_dir / "residential_anchors_v1.csv.gz",
        RESIDENTIAL_ANCHOR_FIELDS,
        (residential_anchor_row(row) for row in realization.anchors),
    )
    _write_csv_gz(
        output_dir / "residential_anchor_evidence_v1.csv.gz",
        RESIDENTIAL_ANCHOR_EVIDENCE_FIELDS,
        (row.to_row() for row in realization.evidence),
    )
    _write_csv_gz(
        output_dir / "materialization_exclusions_v1.csv.gz",
        EXCLUSION_FIELDS,
        (row.to_row() for row in supply.exclusions),
    )


def output_hashes(output_dir: Path) -> dict[str, str]:
    return {name: sha256_file(output_dir / name) for name in OUTPUT_FILES}


def _validation_payload(
    supply: LocationSupplyMaterialization,
    realization: ResidentialAnchorRealization,
    person_households: tuple[str, ...],
) -> dict[str, Any]:
    duplicate_memberships = sum(
        bool(row.potential_duplicate_group_ids) for row in supply.evidence
    )
    return {
        "location_supply_records": len(supply.records),
        "purpose_label_counts": supply.purpose_label_counts(),
        "residential_candidates": len(supply.residential_candidates),
        "residential_anchors": len(realization.anchors),
        "residential_fallback_households": realization.fallback_household_count,
        "persons_reusing_household_anchor": len(person_households),
        "operational_outside_records": 0,
        "attractiveness_nonnull": sum(row.attractiveness is not None for row in supply.records),
        "capacity_nonnull": sum(row.capacity is not None for row in supply.records),
        "records_with_duplicate_diagnostics": duplicate_memberships,
        "exclusions": len(supply.exclusions),
        "status": "PASS",
    }


def _write_checksums(directory: Path) -> None:
    target = directory / "checksums.sha256"
    rows = [
        f"{sha256_file(path)}  {path.name}"
        for path in sorted(directory.iterdir())
        if path.is_file() and path.name != target.name
    ]
    target.write_text("\n".join(rows) + "\n", encoding="utf-8")


def materialize(
    repo_root: Path,
    config_path: Path,
    population_run_dir: Path,
    output_root: Path,
    runbundle_out: Path,
) -> dict[str, Any]:
    pre = precheck(repo_root, config_path, population_run_dir)
    if pre["status"] != "PASS":
        raise RuntimeError(f"F4.1c-C precheck failed: {pre['failed']}")
    implementation_commit = require_frozen_implementation_commit(repo_root)
    cfg = _load_yaml(config_path)

    output_root = output_root.resolve()
    runbundle_out = runbundle_out.resolve()
    if output_root.exists():
        raise FileExistsError(f"Output root already exists: {output_root}")
    if runbundle_out.exists():
        raise FileExistsError(f"RunBundle already exists: {runbundle_out}")
    output_part = output_root.with_name(output_root.name + ".part")
    runbundle_part = runbundle_out.with_name(runbundle_out.name + ".part")
    if output_part.exists() or runbundle_part.exists():
        raise FileExistsError("Existing .part staging path must be resolved manually")

    supply, realization, person_households = _materialize_in_memory(
        repo_root,
        cfg,
        population_run_dir,
    )
    output_part.mkdir(parents=True)
    try:
        _write_outputs(output_part, supply, realization)
        hashes = output_hashes(output_part)
        if set(hashes) != set(OUTPUT_FILES):
            raise AssertionError("Canonical output set mismatch")
        os.replace(output_part, output_root)
    except Exception:
        if output_part.exists():
            shutil.rmtree(output_part)
        raise

    validation = _validation_payload(supply, realization, person_households)
    source = cast(dict[str, Any], cfg["source"])
    runbundle_part.mkdir(parents=True)
    try:
        _write_json(runbundle_part / "environment.json", _environment())
        _write_json(
            runbundle_part / "input_identity.json",
            {
                "source_snapshot_id": source["source_snapshot_id"],
                "osm_sha256": source["sha256"],
                "population_run_dir": str(population_run_dir.resolve()),
            },
        )
        _write_json(runbundle_part / "output_hashes.json", hashes)
        _write_json(runbundle_part / "validation.json", validation)
        _write_json(
            runbundle_part / "run_manifest.json",
            {
                "phase": EXPECTED_PHASE,
                "status": "MATERIALIZATION_PASS_REPRO_PENDING",
                "implementation_commit": implementation_commit,
                "parent_commit": EXPECTED_PARENT,
                "source_snapshot_id": source["source_snapshot_id"],
                "output_root": str(output_root),
                "canonical_output_count": len(OUTPUT_FILES),
                "nonhome_destination_assignments": 0,
                "s_near_executed": False,
                "s_dist_executed": False,
                "s_attr_executed": False,
                "g3_opened": False,
                "mid_test_read": False,
            },
        )
        (runbundle_part / "run.log").write_text(
            f"{datetime.now(UTC).isoformat()} F4.1c-C materialization complete; repro pending\n",
            encoding="utf-8",
        )
        (runbundle_part / "F4_1C_C_MATERIALIZATION_SUMMARY.md").write_text(
            _summary(validation, hashes),
            encoding="utf-8",
        )
        _write_checksums(runbundle_part)
        os.replace(runbundle_part, runbundle_out)
    except Exception:
        if runbundle_part.exists():
            shutil.rmtree(runbundle_part)
        raise

    return {
        "phase": EXPECTED_PHASE,
        "status": "MATERIALIZATION_PASS_REPRO_PENDING",
        "implementation_commit": implementation_commit,
        "output_hashes": hashes,
        "validation": validation,
    }


def repro_check(
    repo_root: Path,
    config_path: Path,
    population_run_dir: Path,
    reference_output: Path,
    runbundle: Path,
) -> dict[str, Any]:
    pre = precheck(repo_root, config_path, population_run_dir)
    if pre["status"] != "PASS":
        raise RuntimeError(f"F4.1c-C precheck failed: {pre['failed']}")
    implementation_commit = require_frozen_implementation_commit(repo_root)
    cfg = _load_yaml(config_path)
    reference_output = reference_output.resolve()
    runbundle = runbundle.resolve()
    if not reference_output.is_dir() or not runbundle.is_dir():
        raise FileNotFoundError("Reference output and RunBundle must already exist")

    manifest = json.loads((runbundle / "run_manifest.json").read_text(encoding="utf-8"))
    if manifest.get("implementation_commit") != implementation_commit:
        raise RuntimeError("RunBundle implementation commit differs from current frozen commit")

    reference_hashes = output_hashes(reference_output)
    second_part = reference_output.with_name(reference_output.name + ".repro.part")
    if second_part.exists():
        raise FileExistsError(f"Existing reproducibility staging directory: {second_part}")
    supply, realization, _ = _materialize_in_memory(repo_root, cfg, population_run_dir)
    second_part.mkdir(parents=True)
    try:
        _write_outputs(second_part, supply, realization)
        second_hashes = output_hashes(second_part)
    finally:
        if second_part.exists():
            shutil.rmtree(second_part)

    matched = reference_hashes == second_hashes
    reproduction = {
        "status": "PASS" if matched else "FAIL",
        "implementation_commit": implementation_commit,
        "reference_hashes": reference_hashes,
        "second_run_hashes": second_hashes,
        "exact_sha256_match": matched,
    }
    _write_json(runbundle / "reproducibility.json", reproduction)
    manifest["status"] = "PASS" if matched else "FAIL_REPRODUCIBILITY"
    manifest["reproducibility_exact_sha256_match"] = matched
    _write_json(runbundle / "run_manifest.json", cast(dict[str, Any], manifest))
    with (runbundle / "run.log").open("a", encoding="utf-8") as handle:
        handle.write(
            f"{datetime.now(UTC).isoformat()} reproducibility exact_sha256_match={matched}\n"
        )
    _write_checksums(runbundle)
    if not matched:
        raise RuntimeError("F4.1c-C exact-output reproducibility check failed")
    return reproduction


def _summary(validation: dict[str, Any], hashes: dict[str, str]) -> str:
    lines = [
        "# F4.1c-C Materialization Summary",
        "",
        "**State:** materialization complete; exact reproducibility rerun pending.",
        "",
        "## Counts",
        "",
        f"- Operational LocationSupply records: `{validation['location_supply_records']}`",
        f"- Residential candidates: `{validation['residential_candidates']}`",
        f"- Residential anchors: `{validation['residential_anchors']}`",
        f"- Persons reusing household HOME anchor: `{validation['persons_reusing_household_anchor']}`",
        f"- Landuse fallback households: `{validation['residential_fallback_households']}`",
        "",
        "## Canonical output SHA-256",
        "",
    ]
    for name, digest in sorted(hashes.items()):
        lines.append(f"- `{name}`: `{digest}`")
    lines.extend(
        [
            "",
            "## Boundary",
            "",
            "No non-home destination assignment, S_NEAR, S_DIST, S_ATTR, G3 or MiD TEST access occurred.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    parser.add_argument("--population-run-dir", required=True)
    parser.add_argument("--output-root")
    parser.add_argument("--runbundle-out")
    parser.add_argument("--reference-output")
    parser.add_argument("--runbundle")
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--precheck", action="store_true")
    modes.add_argument("--materialize", action="store_true")
    modes.add_argument("--repro-check", action="store_true")
    args = parser.parse_args()

    repo_root = Path.cwd().resolve()
    config_path = (repo_root / args.config).resolve()
    population_run_dir = Path(args.population_run_dir).resolve()
    if args.precheck:
        result = precheck(repo_root, config_path, population_run_dir)
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0 if result["status"] == "PASS" else 1
    if args.materialize:
        if not args.output_root or not args.runbundle_out:
            parser.error("--output-root and --runbundle-out are required with --materialize")
        result = materialize(
            repo_root,
            config_path,
            population_run_dir,
            repo_root / args.output_root,
            repo_root / args.runbundle_out,
        )
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    if not args.reference_output or not args.runbundle:
        parser.error("--reference-output and --runbundle are required with --repro-check")
    result = repro_check(
        repo_root,
        config_path,
        population_run_dir,
        repo_root / args.reference_output,
        repo_root / args.runbundle,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
