"""Only frozen F4.1c-C canonical 4 CSV.gz files; deterministic output bytes."""
from __future__ import annotations

import csv
import gzip
import hashlib
import io
import json
import math
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pyproj import Transformer

from simfleet_edg.canonical.mobility import LocationRef, LocationSupplyRecord, ResidentialAnchor
from simfleet_edg.spatial.candidate_index import Candidate, CandidateIndex
from simfleet_edg.spatial.candidate_policies import attractive_midrank_weights

FROZEN_C_SHA: dict[str, str] = {
    "location_supply_v1.csv.gz": "6ffba6fd100b4add61da84b270da34dacadbbda3dbffd0c91fb065bed67b054e",
    "location_supply_evidence_v1.csv.gz": "4ae37068bfd65d777ee697a2fda5ad5107f80790f98d7ecec255003979e9e9a3",
    "residential_anchors_v1.csv.gz": "a19f58eaa17905b66f9a02152c432667cf4f2ca04580025238137bfa3f00abf0",
    "residential_anchor_evidence_v1.csv.gz": "63310a328f9aff82652b67b2a7c0efdcf16dd2d7ccd61c66c5bfefe55f361d50",
}
PURPOSES = frozenset({"WORK_COMMUTE", "EDUCATION", "BUSINESS", "SHOPPING", "LEISURE", "OTHER"})


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def frozen_input_gate(directory: Path) -> None:
    for name, expected in FROZEN_C_SHA.items():
        p = directory / name
        if not p.is_file() or digest(p) != expected:
            raise ValueError(f"FROZEN_C_HASH_MISMATCH: {p}")


def read_gz_rows(path: Path) -> list[dict[str, str]]:
    with gzip.open(path, "rt", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _blank(value: str | None) -> bool:
    return value is None or value.strip().lower() in {"", "none", "null", "nan"}


def _float_or_none(value: str | None) -> float | None:
    return None if _blank(value) else float(str(value))


@dataclass(frozen=True, slots=True)
class FrozenSupply:
    records: tuple[LocationSupplyRecord, ...]
    anchors: dict[str, ResidentialAnchor]
    indices: dict[str, CandidateIndex]
    locations: dict[str, LocationRef]
    evidence: dict[str, dict[str, str]]


def load_frozen_supply(directory: Path, *, verify_hashes: bool = True,
                       expected_supply: int = 88879,
                       expected_anchors: int = 54828) -> FrozenSupply:
    if verify_hashes:
        frozen_input_gate(directory)
    raw = read_gz_rows(directory / "location_supply_v1.csv.gz")
    evid = read_gz_rows(directory / "location_supply_evidence_v1.csv.gz")
    home = read_gz_rows(directory / "residential_anchors_v1.csv.gz")
    home_evidence = read_gz_rows(directory / "residential_anchor_evidence_v1.csv.gz")
    if len(raw) != expected_supply or len(evid) != expected_supply:
        raise ValueError("Canonical C supply/evidence cardinality mismatch")
    if len(home) != expected_anchors or len(home_evidence) != expected_anchors:
        raise ValueError("Canonical C residential anchors/evidence cardinality mismatch")
    evid_by_id = {r["location_id"]: r for r in evid}
    if len(evid_by_id) != len(evid):
        raise ValueError("Duplicate C evidence location_id")
    home_evidence_ids = {r["household_id"] for r in home_evidence}
    if len(home_evidence_ids) != len(home_evidence):
        raise ValueError("Duplicate C anchor evidence household_id")
    records: list[LocationSupplyRecord] = []
    locations: dict[str, LocationRef] = {}
    for row in raw:
        ident = row["location_id"]
        if ident in locations or ident not in evid_by_id:
            raise ValueError("C supply duplicate or missing evidence")
        ref = LocationRef(ident, row["level"], float(row["lon"]), float(row["lat"]), row["crs"])
        purposes = tuple(str(p) for p in json.loads(row["eligible_purposes_json"]))
        if ref.crs != "EPSG:4326" or not set(purposes).issubset(PURPOSES):
            raise ValueError("C supply CRS/eligibility out of contract")
        attr = _float_or_none(row.get("attractiveness"))
        cap = _float_or_none(row.get("capacity"))
        if attr is not None or cap is not None:
            raise ValueError("Frozen C supply must have NULL attractiveness/capacity")
        ev = evid_by_id[ident]
        if not ev["plr_id"] or ev["plr_id"] == "OUTSIDE":
            raise ValueError("C operational supply outside frozen Berlin PLR")
        records.append(LocationSupplyRecord(ref, purposes, None, None, row["provenance"]))
        locations[ident] = ref
    if set(locations) != set(evid_by_id):
        raise ValueError("C evidence identities must match supply exactly")
    anchors: dict[str, ResidentialAnchor] = {}
    for row in home:
        hh = row["household_id"]
        if hh in anchors or hh not in home_evidence_ids:
            raise ValueError("C anchor duplicate or missing evidence")
        ref = LocationRef(row["location_id"], row["level"], float(row["lon"]),
                          float(row["lat"]), row["crs"])
        if ref.crs != "EPSG:4326":
            raise ValueError("Frozen C HOME must be in EPSG:4326")
        anchors[hh] = ResidentialAnchor(hh, ref, row["parent_bezirk_id"], row["provenance"])
    transform = Transformer.from_crs("EPSG:4326", "EPSG:25833", always_xy=True)
    by_purpose: dict[str, list[LocationSupplyRecord]] = {p: [] for p in PURPOSES}
    for rec in records:
        for purpose in rec.eligible_purposes:
            by_purpose[purpose].append(rec)
    indices: dict[str, CandidateIndex] = {}
    for purpose, recs in sorted(by_purpose.items()):
        if not recs:
            raise ValueError(f"No frozen citywide C supply for {purpose}")
        areas = {r.location.location_id:
                 (_float_or_none(evid_by_id[r.location.location_id].get("projected_area_m2"))
                  if evid_by_id[r.location.location_id]["geometry_kind"] == "POLYGON" else None)
                 for r in recs}
        weights = attractive_midrank_weights(areas)
        candidates = []
        for rec in recs:
            x, y = transform.transform(rec.location.lon, rec.location.lat)
            if not math.isfinite(x) or not math.isfinite(y):
                raise ValueError("Invalid projected C coordinate")
            candidates.append(Candidate(rec.location.location_id, float(x), float(y),
                                        weights[rec.location.location_id]))
        indices[purpose] = CandidateIndex(candidates)
    return FrozenSupply(tuple(records), anchors, indices, locations, evid_by_id)


def write_gzip_rows(path: Path, columns: tuple[str, ...],
                    rows: Iterable[Mapping[str, Any]]) -> None:
    if path.exists():
        raise FileExistsError(f"No output overwrite: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=list(columns), extrasaction="raise", lineterminator="\n")
    writer.writeheader()
    for row in rows:
        writer.writerow(row)
    with path.open("wb") as raw:
        with gzip.GzipFile(fileobj=raw, mode="wb", filename="", mtime=0) as gz:
            gz.write(buffer.getvalue().encode("utf-8"))


def write_json(path: Path, payload: Mapping[str, Any]) -> None:
    if path.exists():
        raise FileExistsError(f"No output overwrite: {path}")
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n",
                    encoding="utf-8")
