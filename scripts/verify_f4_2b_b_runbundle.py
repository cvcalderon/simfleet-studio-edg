"""Read-only canonical F4.2b-B RunBundle verifier (all 11 scenarios)."""
from __future__ import annotations

import argparse
import csv
import gzip
import json
from collections import Counter
from pathlib import Path
from typing import Any

from simfleet_edg.spatial.escort_day_binding import VARIANTS
from simfleet_edg.spatial.spatial_core_io import digest


def _count(path: Path, key: str) -> tuple[int, Counter[str]]:
    counters: Counter[str] = Counter()
    with gzip.open(path, "rt", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        n = 0
        for row in reader:
            n += 1
            counters[row[key]] += 1
    return n, counters


def _filehashes(root: Path) -> dict[str, str]:
    return {p.relative_to(root).as_posix(): digest(p) for p in sorted(root.rglob("*"))
            if p.is_file()}


def verify(bundle: Path) -> dict[str, Any]:
    manifest = json.loads((bundle / "run_manifest_v1.json").read_text())
    if (manifest["status"] != "RETURN_TO_MAIN_NO_G3"
            or manifest["science_class"] != "SYNTHETIC_HYPOTHETICAL_NOT_OBSERVED"
            or manifest["variant_ids"] != list(VARIANTS)
            or not manifest["two_independent_runs_byte_exact"]
            or manifest["g3_opened"] or manifest["f4_2c_opened"]):
        raise RuntimeError("BLOCKED_F4_2B_B_BUNDLE_PROVENANCE")
    a = _filehashes(bundle / "A")
    b = _filehashes(bundle / "B")
    if len(a) != 44 or a != b or a != manifest["sha256_canonical_by_relative_path"]:
        raise RuntimeError("BLOCKED_F4_2B_B_AB_BYTE_IDENTITY")
    frozen = json.loads((bundle / "runbundle_sha256_v1.json").read_text())
    if frozen != {path: value for path, value in _filehashes(bundle).items()
                  if path != "runbundle_sha256_v1.json"}:
        raise RuntimeError("BLOCKED_F4_2B_B_BUNDLE_SHA")
    for variant in VARIANTS:
        folder = bundle / "A" / variant
        nd, ds = _count(folder / "day_ledger_v1.csv.gz", "day_status")
        nt, ts = _count(folder / "trip_ledger_v1.csv.gz", "spatial_status")
        delta, _ = _count(folder / "escort_spatialized_trip_delta_v1.csv.gz", "variant_id")
        if (nd, nt, ds["CORE_FROZEN_SPATIALIZED"], ts["CORE_BY_REFERENCE"]) != (
                100000, 325613, 84619, 240751):
            raise RuntimeError("BLOCKED_F4_2B_B_FULL_LEDGER_COUNT: " + variant)
        if (sum(ds.values()) != 100000 or delta != ts["ESCORT_SPATIALIZED"]
                or ts["ESCORT_SPATIALIZED"] + ts["ESCORT_UNSPATIALIZED"] != 84862
                or any("PENDING" in state or "FATAL" in state for state in ds)):
            raise RuntimeError("BLOCKED_F4_2B_B_PARTITION: " + variant)
        metrics = json.loads((folder / "variant_scientific_summary_v1.json").read_text())
        if (metrics["variant_id"] != variant or metrics["real_person_linkage_observed"]
                or metrics["experimental_variant_selected"]):
            raise RuntimeError("BLOCKED_F4_2B_B_UNSUPPORTED_SCIENCE")
    return {"status": "F4_2B_B_RUNBUNDLE_VERIFIER_PASS", "variants": len(VARIANTS),
            "independent_runs": 2, "canonical_paths_per_run": len(a),
            "original_events_each": 18871, "full_days_each": 100000,
            "full_trips_each": 325613, "g3_opened": False}


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--runbundle", type=Path, required=True)
    args = p.parse_args()
    print(json.dumps(verify(args.runbundle), sort_keys=True))


if __name__ == "__main__":
    main()
