"""F4.2b-A LOCAL-ONLY reproducible ESCORT location sensitivity; POST-PUSH ONLY.

Reads immutable M1/C and F4.2a bundle, never recomputes D_GEN/F4.2a,
never accesses CAL/MiD TEST and never selects or validates real human links.
"""
from __future__ import annotations

import argparse
import csv
import gzip
import io
import json
import os
import subprocess
import sys
from collections import Counter
from pathlib import Path
from typing import Any

import yaml  # type: ignore[import-untyped]

from simfleet_edg.spatial.escort_event_index import index_frozen_m2
from simfleet_edg.spatial.escort_location_binding import inherit_location
from simfleet_edg.spatial.escort_synthetic_relations import (
    PROVENANCE,
    PartnerPools,
    load_variants,
    propose,
)
from simfleet_edg.spatial.escort_target_anchor_extension import (
    AnchorAssignment,
    extend_stable_anchors,
    read_core_stable,
)
from simfleet_edg.spatial.spatial_core_io import (
    digest,
    frozen_input_gate,
    load_frozen_supply,
    write_json,
)

PARENT = "7ec2c7aa884191ec77cf1fe6783756b78471f9c3"
SCENARIO = "F4_2A_CORE_REFERENCE_V1"
DAY = "F4_2A_CORE_REFERENCE_DAY_01"
FORBIDDEN = ("MID_TEST", "MIDTH", "CALIBRATION", "/CAL/", "/TEST/")
PROPOSAL_COLUMNS = ("variant_id", "row_id", "trip_index", "event_id", "escort_person_id",
    "escort_household_id", "original_destination_activity", "original_arrival_absolute_minute",
    "original_departure_clock_minute", "target_purpose", "scope", "target_person_id",
    "target_location_id", "status", "evidence_class", "source_prior_sha256",
    "draw_stream_namespace", "temporal_claim", "household_size_class", "resource_state")


def safe_path(path: Path) -> Path:
    result = path.expanduser().absolute()
    if any(token in str(result).upper() for token in FORBIDDEN):
        raise ValueError("Forbidden CAL/MiD TEST source or output path")
    return result


def git_gate(repo: Path) -> dict[str, str]:
    def git(*args: str) -> str:
        return subprocess.check_output(["git", *args], cwd=repo, text=True).strip()
    head, origin = git("rev-parse", "HEAD"), git("rev-parse", "refs/remotes/origin/main")
    parent = git("rev-parse", "HEAD^")
    changes = [x.split("\t", 1) for x in git("diff-tree", "--no-commit-id", "--name-status", "-r", "HEAD").splitlines()]
    expected = set((repo / "docs/F4_2B_A_LOCAL_OVERLAY_FILELIST_v1.txt").read_text().splitlines())
    if (git("branch", "--show-current") != "main" or head != origin
        or parent != PARENT or git("status", "--porcelain", "--untracked-files=all")
        or len(expected) != 20 or len(changes) != 20 or
        any(status != "A" for status, _ in changes) or {p for _, p in changes} != expected):
        raise RuntimeError("F4_2B_A_POSTPUSH_GIT_EXACT_SCOPE_BLOCKED")
    lines = (repo / "docs/F4_2B_A_LOCAL_OVERLAY_CHECKSUMS_v1.sha256").read_text().splitlines()
    validated: set[str] = set()
    for line in lines:
        sha256, rel = line.split("  ", 1)
        if rel not in expected or rel in validated or digest(repo / rel) != sha256:
            raise RuntimeError("F4_2B_A_POSTPUSH_OVERLAY_HASH_MISMATCH: " + rel)
        validated.add(rel)
    if validated != expected - {"docs/F4_2B_A_LOCAL_OVERLAY_CHECKSUMS_v1.sha256"}:
        raise RuntimeError("F4_2B_A_POSTPUSH_OVERLAY_MANIFEST_INCOMPLETE")
    return {"head": head, "origin_main": origin, "parent": parent}


def config(repo: Path) -> dict[str, Any]:
    data: dict[str, Any] = yaml.safe_load((repo / "configs/f4/f4_2b_a_local_sensitivity_preopen_v1.yaml").read_text())
    if data["evidence_class"] != PROVENANCE or data["selected_spatial_policy"] != "S_DIST":
        raise ValueError("Wrong frozen scientific contract")
    return data


def hash_gate(root: Path, expected: dict[str, str]) -> None:
    for rel, checksum in expected.items():
        p = root / rel
        if not p.is_file() or digest(p) != checksum:
            raise RuntimeError(f"FROZEN_INPUT_SHA256_MISMATCH: {rel}")


def prior_gate(sources: Path, cfg: dict[str, Any]) -> None:
    hash_gate(sources, cfg["source_files_sha256"])
    if digest(sources / "F4_2B_A_LOCAL_SOURCE_PRIOR_BUNDLE_v1.yaml") != cfg["source_bundle_sha256"]:
        raise RuntimeError("FROZEN_SOURCE_PRIOR_BUNDLE_SHA256_MISMATCH")


def load_m1(pop: Path, cfg: dict[str, Any], idx_households: dict[str, str]) -> dict[str, str]:
    hash_gate(pop, cfg["m1_sha256"])
    with (pop / "M_P_CONSTR_RMIN_V2_HD_U_persons.csv").open(newline="", encoding="utf-8") as file:
        people = {r["person_id"]: r["household_id"] for r in csv.DictReader(file)}
    if len(people) != 100000 or people != idx_households:
        raise ValueError("Full accepted M1 identity mapping mismatch frozen M2")
    return people


def write_gzip_stream(path: Path, columns: tuple[str, ...], rows: Any) -> None:
    if path.exists():
        raise FileExistsError(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as raw:
        with gzip.GzipFile(filename="", fileobj=raw, mode="wb", mtime=0) as gz:
            with io.TextIOWrapper(gz, encoding="utf-8", newline="", write_through=True) as text:
                writer = csv.DictWriter(text, fieldnames=columns, extrasaction="raise", lineterminator="\n")
                writer.writeheader()
                writer.writerows(rows)


def _anchor_record(a: AnchorAssignment) -> dict[str, str | float]:
    return {"person_id": a.person_id, "purpose": a.purpose,
            "location_id": a.location_id, "prior_aggregate_km": a.prior_aggregate_km,
            "origin": a.origin}


def run_single(repo: Path, pop: Path, c_out: Path, frozen: Path,
               sources: Path, dest: Path, *, strict: bool = True) -> dict[str, Any]:
    if dest.exists():
        raise FileExistsError("One-run output must be a fresh directory")
    cfg = config(repo)
    hash_gate(frozen, cfg["runbundle_sha256"])
    prior_gate(sources, cfg)
    frozen_input_gate(c_out)
    idx = index_frozen_m2(frozen / "dgen_A/dgen_day_rows_v1.csv.gz",
                          frozen / "dgen_A/dgen_trip_rows_v1.csv.gz", enforce_100k=strict)
    _ = load_m1(pop, cfg, idx.person_households)
    core = read_core_stable(frozen / "spatial_1/S_DIST/core_stable_locations_S_DIST_v1.csv.gz")
    supply = load_frozen_supply(c_out)
    all_anchors, sidecar = extend_stable_anchors(idx, supply, core)
    pools = PartnerPools(idx, all_anchors)
    context: dict[str, tuple[str, str]] = {}
    with gzip.open(frozen / "dgen_A/dgen_context_v1.csv.gz", "rt", encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            rid = row["row_id"]
            if rid in context:
                raise ValueError("Duplicate frozen context row ID")
            # Preserve UNKNOWN, 6_PLUS and literal categoricals; never coerce to binary.
            context[rid] = (row["household_size_class"], row["person_car_access"])
    if len(context) != 100000 or any(e.row_id not in context for e in idx.events):
        raise ValueError("Frozen M2 context identity coverage mismatch")
    variants = load_variants(sources / "F4_2B_A_LOCAL_VARIANT_MATRIX_v1.csv")
    if len(idx.events) != 18871 or len(variants) != 10:
        raise ValueError("Exact pre-registered events/variants missing")
    dest.mkdir(parents=True)
    write_gzip_stream(dest / "target_stable_anchor_extension_v1.csv.gz",
        ("person_id", "purpose", "location_id", "prior_aggregate_km", "origin"),
        (_anchor_record(r) for r in sidecar))
    # All target LocationRefs must come exclusively from the original C supply.
    for a in sidecar:
        inherit_location(a, supply.locations)
    summaries: list[dict[str, str | int | float]] = []
    for variant in (None, *variants):
        name = "B0_NO_LINK" if variant is None else variant.variant_id
        statuses: Counter[str] = Counter()
        chosen: Counter[str] = Counter()
        by_stratum: dict[str, Counter[str]] = {}
        def records() -> Any:
            for e in idx.events:
                proposal = propose(e, variant, pools, all_anchors, scenario=SCENARIO,
                                   day=DAY, prior_sha=cfg["source_bundle_sha256"])
                hh_size, resource = context[e.row_id]
                proposal["household_size_class"] = hh_size
                proposal["resource_state"] = resource
                strata_key = f"{hh_size}|{resource}"
                if strata_key not in by_stratum:
                    by_stratum[strata_key] = Counter()
                by_stratum[strata_key][proposal["status"]] += 1
                statuses[proposal["status"]] += 1
                chosen[proposal["target_purpose"]] += 1
                if proposal["target_location_id"]:
                    key = (proposal["target_person_id"],
                           "WORK_COMMUTE" if proposal["target_purpose"] == "WORK" else "EDUCATION")
                    bound = inherit_location(all_anchors[key], supply.locations)
                    if bound.location_id != proposal["target_location_id"]:
                        raise ValueError("LocationRef inheritance mismatch")
                yield proposal
        target = dest / f"escort_location_proposals_{name}_v1.csv.gz"
        write_gzip_stream(target, PROPOSAL_COLUMNS, records())
        if sum(statuses.values()) != len(idx.events):
            raise ValueError("One row per ESCORT event contract broken")
        audit: dict[str, Any] = {"variant_id": name, "total_escort_events": len(idx.events),
            "statuses": dict(sorted(statuses.items())), "purpose_draws": dict(sorted(chosen.items())),
            "statuses_by_household_and_resource": {k: dict(sorted(v.items())) for k, v in sorted(by_stratum.items())},
            "source_prior_sha256": cfg["source_bundle_sha256"],
            "evidence_class": PROVENANCE, "link_claim": "LOCATION_ONLY_NOT_OBSERVED",
            "home_identification": "NOT_IDENTIFIED_NOT_ZERO",
            "scientific_selection": "MAIN_ONLY_NOT_SELECTED", "cal_reads": 0, "mid_test_reads": 0}
        if variant is not None:
            audit.update({"year": variant.year, "household_share_hypothesis": variant.p_household,
                "external_descriptive_transfer": {
                    "EDUCATION": variant.p_education, "WORK": variant.p_work,
                    "UNSUPPORTED_PURPOSE": variant.p_unsupported}})
        write_json(dest / f"escort_audit_{name}_v1.json", audit)
        summaries.append({"variant_id": name, "events": len(idx.events),
            "resolved_location_only": statuses["RESOLVED_LOCATION_ONLY"],
            "unresolved_unsupported": statuses["UNRESOLVED_UNSUPPORTED_PURPOSE"],
            "unresolved_scope": statuses["UNRESOLVED_NO_ELIGIBLE_PARTNER"],
            "unresolved_anchor": statuses["UNRESOLVED_TARGET_ANCHOR"],
            "unresolved_B0": statuses["UNRESOLVED_B0_NO_LINK"]})
    write_gzip_stream(dest / "all_variant_summary_v1.csv.gz",
        ("variant_id", "events", "resolved_location_only", "unresolved_unsupported",
         "unresolved_scope", "unresolved_anchor", "unresolved_B0"), summaries)
    manifest = {"status": "EXPLORATORY_RETURN_TO_MAIN_NO_PROMOTION",
        "evidence_class": PROVENANCE, "baseline": SCENARIO,
        "frozen_m2": {"days": idx.day_count, "trips": idx.trip_count,
                      "escort_events": len(idx.events), "escort_days": idx.escort_day_count,
                      "escort_day_trips": idx.escort_day_trip_count},
        "frozen_input_sha256": cfg["runbundle_sha256"],
        "variant_count_including_B0": len(summaries), "stable_core_count": len(core),
        "stable_sidecar_count": len(sidecar), "g3_opened": False, "cal_reads": 0,
        "mid_test_reads": 0, "real_person_link_validation": False}
    write_json(dest / "scientific_return_to_main_v1.json", manifest)
    return manifest


def file_hashes(root: Path) -> dict[str, str]:
    return {p.relative_to(root).as_posix(): digest(p) for p in sorted(root.rglob("*")) if p.is_file()}


def main() -> None:
    parser = argparse.ArgumentParser()
    for arg in ("repo", "population", "c-output", "runbundle", "source-priors", "output"):
        parser.add_argument("--" + arg, required=True)
    parser.add_argument("--stage", choices=("full", "single", "precheck"), default="full")
    args = parser.parse_args()
    repo, pop, c_out, frozen, priors, output = [safe_path(Path(p)) for p in (
        args.repo, args.population, args.c_output, args.runbundle,
        args.source_priors, args.output)]
    if output.exists() or output.with_name(output.name + ".partial").exists():
        raise FileExistsError("Nonempty/previous output path; no overwrites")
    git = git_gate(repo)
    cfg = config(repo)
    hash_gate(frozen, cfg["runbundle_sha256"])
    prior_gate(priors, cfg)
    hash_gate(pop, cfg["m1_sha256"])
    frozen_input_gate(c_out)
    if args.stage == "precheck":
        print(json.dumps({"status": "PRECHECK_PASS", "git": git,
                          "frozen": len(cfg["runbundle_sha256"])}, sort_keys=True))
        return
    if args.stage == "single":
        run_single(repo, pop, c_out, frozen, priors, output)
        print("F4_2B_A_ONE_RUN_PASS")
        return
    staging = output.with_name(output.name + ".partial")
    staging.mkdir(parents=True)
    for label in ("A", "B"):
        cmd = [sys.executable, "-m", "simfleet_edg.repro.f4_2b_a_local_sensitivity",
            "--repo", str(repo), "--population", str(pop), "--c-output", str(c_out),
            "--runbundle", str(frozen), "--source-priors", str(priors),
            "--output", str(staging / label), "--stage", "single"]
        subprocess.run(cmd, check=True, cwd=repo)
    a, b = file_hashes(staging / "A"), file_hashes(staging / "B")
    if a != b or not a or len(a) != 25:
        raise RuntimeError("BLOCKED_REPRO: full A/B canonical outputs differ")
    write_json(staging / "runbundle_manifest_v1.json", {
        "status": "RETURN_TO_MAIN_NO_G3", "git": git, "pair_exact": True,
        "files_per_run": len(a), "sha256_by_relative_path": a,
        "evidence_class": PROVENANCE, "no_data_regeneration": True,
        "scientific_candidate_selected": False})
    write_json(staging / "runbundle_all_checksums_v1.json", file_hashes(staging))
    os.replace(staging, output)
    print("F4_2B_A_RUNBUNDLE_RETURN_TO_MAIN_NO_G3")


if __name__ == "__main__":
    main()
