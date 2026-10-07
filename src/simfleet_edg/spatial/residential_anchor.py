from __future__ import annotations

import hashlib
import importlib
import math
from dataclasses import dataclass
from typing import Any, Final

from simfleet_edg.canonical.mobility import LocationRef, ResidentialAnchor
from simfleet_edg.spatial.location_supply import ResidentialSupplyCandidate
from simfleet_edg.spatial.lor_lookup import (
    EXPECTED_M1_BEZIRK_IDS,
    FrozenLorLookup,
    m1_bezirk_code2d,
    validate_m1_bezirk_id,
)

SOURCE_CRS: Final[str] = "EPSG:4326"
HOME_LEVEL: Final[str] = "SYNTHETIC_HOME"
SELECTION_NAMESPACE: Final[str] = "F4_1C_C_RESIDENTIAL_ANCHOR_V1"
FALLBACK_MAX_ATTEMPTS: Final[int] = 10_000

CsvScalar = str | int | float | None
CsvRow = dict[str, CsvScalar]


@dataclass(frozen=True, slots=True)
class HouseholdHomeInput:
    household_id: str
    home_zone_level: str
    home_zone_id: str

    def __post_init__(self) -> None:
        if not self.household_id:
            raise ValueError("household_id must be non-empty")
        if self.home_zone_level != "BEZIRK":
            raise ValueError("F4.1c-C requires M1 home_zone_level=BEZIRK")
        validate_m1_bezirk_id(self.home_zone_id)


@dataclass(frozen=True, slots=True)
class ResidentialAnchorEvidence:
    household_id: str
    source_candidate_id: str
    source_snapshot_id: str
    osm_element_type: str
    osm_element_id: int
    supply_class: str
    pool_class_used: str
    candidate_count_in_pool: int
    pool_total_mass_m2: float
    candidate_allocation_mass_m2: float
    selection_namespace: str
    selection_hash_sha256: str
    point_method: str
    point_attempt_index: int | None
    parent_bezirk_code_2d: str
    realized_plr_id: str
    realized_lor_bzr_id: str
    realized_pgr_id: str
    provenance: str

    def to_row(self) -> CsvRow:
        return {
            "household_id": self.household_id,
            "source_candidate_id": self.source_candidate_id,
            "source_snapshot_id": self.source_snapshot_id,
            "osm_element_type": self.osm_element_type,
            "osm_element_id": self.osm_element_id,
            "supply_class": self.supply_class,
            "pool_class_used": self.pool_class_used,
            "candidate_count_in_pool": self.candidate_count_in_pool,
            "pool_total_mass_m2": self.pool_total_mass_m2,
            "candidate_allocation_mass_m2": self.candidate_allocation_mass_m2,
            "selection_namespace": self.selection_namespace,
            "selection_hash_sha256": self.selection_hash_sha256,
            "point_method": self.point_method,
            "point_attempt_index": self.point_attempt_index,
            "parent_bezirk_code_2d": self.parent_bezirk_code_2d,
            "realized_plr_id": self.realized_plr_id,
            "realized_lor_bzr_id": self.realized_lor_bzr_id,
            "realized_pgr_id": self.realized_pgr_id,
            "provenance": self.provenance,
        }


@dataclass(frozen=True, slots=True)
class ResidentialAnchorRealization:
    anchors: tuple[ResidentialAnchor, ...]
    evidence: tuple[ResidentialAnchorEvidence, ...]

    @property
    def fallback_household_count(self) -> int:
        return sum(row.pool_class_used == "AREA_FALLBACK" for row in self.evidence)


def realize_residential_anchors(
    *,
    households: tuple[HouseholdHomeInput, ...],
    candidates: tuple[ResidentialSupplyCandidate, ...],
    lor_lookup: FrozenLorLookup,
    source_snapshot_id: str,
    require_all_frozen_boroughs: bool = True,
) -> ResidentialAnchorRealization:
    _validate_households(households)
    pools = _candidate_pools(candidates)
    if require_all_frozen_boroughs:
        missing = [
            full14
            for full14 in EXPECTED_M1_BEZIRK_IDS
            if not pools.get(full14, {}).get("RESIDENTIAL_BUILDING")
        ]
        if missing:
            raise ValueError(f"Frozen source lacks residential building support: {missing}")

    anchors: list[ResidentialAnchor] = []
    evidence: list[ResidentialAnchorEvidence] = []
    provenance = f"F4.1c-C|{source_snapshot_id}|RESIDENTIAL_ANCHOR_V1"

    for household in sorted(households, key=lambda row: row.household_id):
        parent = validate_m1_bezirk_id(household.home_zone_id)
        parent_pools = pools.get(parent, {})
        building = parent_pools.get("RESIDENTIAL_BUILDING", ())
        fallback = parent_pools.get("RESIDENTIAL_AREA_FALLBACK", ())
        if building:
            pool = building
            pool_class = "BUILDING"
        elif fallback:
            pool = fallback
            pool_class = "AREA_FALLBACK"
        else:
            raise ValueError(f"No residential candidate pool for M1 borough {parent}")

        chosen, selection_digest, total_mass = _select_candidate(
            household.household_id,
            parent,
            pool,
        )
        if pool_class == "BUILDING":
            point_25833 = chosen.geometry_25833.representative_point()
            point_method = "POINT_ON_SURFACE"
            attempt_index: int | None = None
        else:
            point_25833, point_method, attempt_index = _fallback_point(
                household.household_id,
                chosen,
            )

        point_4326 = lor_lookup.to_source_geometry(point_25833)
        lon = float(point_4326.x)
        lat = float(point_4326.y)
        if not math.isfinite(lon) or not math.isfinite(lat):
            raise ValueError(f"Non-finite residential anchor for {household.household_id}")
        assignment = lor_lookup.locate(lon, lat)
        if assignment is None:
            raise ValueError(f"Residential anchor outside frozen LOR: {household.household_id}")
        code2d = m1_bezirk_code2d(parent)
        if assignment.plr_id[:2] != code2d or assignment.lor_bzr_id[:2] != code2d:
            raise ValueError(
                f"Residential anchor parent mismatch for {household.household_id}: "
                f"M1={code2d} PLR={assignment.plr_id} BZR={assignment.lor_bzr_id}"
            )

        location = LocationRef(
            location_id=f"home:{household.household_id}",
            level=HOME_LEVEL,
            lon=lon,
            lat=lat,
            crs=SOURCE_CRS,
        )
        anchor = ResidentialAnchor(
            household_id=household.household_id,
            location=location,
            parent_bezirk_id=parent,
            provenance=provenance,
        )
        anchors.append(anchor)
        evidence.append(
            ResidentialAnchorEvidence(
                household_id=household.household_id,
                source_candidate_id=chosen.candidate_id,
                source_snapshot_id=source_snapshot_id,
                osm_element_type=chosen.osm_element_type,
                osm_element_id=chosen.osm_element_id,
                supply_class=chosen.supply_class,
                pool_class_used=pool_class,
                candidate_count_in_pool=len(pool),
                pool_total_mass_m2=total_mass,
                candidate_allocation_mass_m2=chosen.allocation_area_m2,
                selection_namespace=SELECTION_NAMESPACE,
                selection_hash_sha256=selection_digest,
                point_method=point_method,
                point_attempt_index=attempt_index,
                parent_bezirk_code_2d=code2d,
                realized_plr_id=assignment.plr_id,
                realized_lor_bzr_id=assignment.lor_bzr_id,
                realized_pgr_id=assignment.pgr_id,
                provenance=provenance,
            )
        )

    if len(anchors) != len(households):
        raise AssertionError("Residential anchor cardinality mismatch")
    return ResidentialAnchorRealization(tuple(anchors), tuple(evidence))


def residential_anchor_row(anchor: ResidentialAnchor) -> CsvRow:
    return {
        "household_id": anchor.household_id,
        "location_id": anchor.location.location_id,
        "level": anchor.location.level,
        "lon": anchor.location.lon,
        "lat": anchor.location.lat,
        "crs": anchor.location.crs,
        "parent_bezirk_id": anchor.parent_bezirk_id,
        "provenance": anchor.provenance,
    }


def _validate_households(households: tuple[HouseholdHomeInput, ...]) -> None:
    ids = [row.household_id for row in households]
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate household_id in accepted M1 input")
    for row in households:
        if row.home_zone_level != "BEZIRK":
            raise ValueError("Accepted M1 input contains non-BEZIRK home_zone_level")
        validate_m1_bezirk_id(row.home_zone_id)


def _candidate_pools(
    candidates: tuple[ResidentialSupplyCandidate, ...],
) -> dict[str, dict[str, tuple[ResidentialSupplyCandidate, ...]]]:
    mutable: dict[str, dict[str, list[ResidentialSupplyCandidate]]] = {}
    for candidate in candidates:
        if candidate.supply_class not in {
            "RESIDENTIAL_BUILDING",
            "RESIDENTIAL_AREA_FALLBACK",
        }:
            raise ValueError(f"Unknown residential supply class: {candidate.supply_class}")
        parent = validate_m1_bezirk_id(candidate.parent_m1_bezirk_id)
        if candidate.parent_bezirk_code_2d != parent[-2:]:
            raise ValueError(f"Residential candidate parent mismatch: {candidate.candidate_id}")
        if not math.isfinite(candidate.allocation_area_m2) or candidate.allocation_area_m2 <= 0.0:
            raise ValueError(f"Invalid residential allocation mass: {candidate.candidate_id}")
        mutable.setdefault(parent, {}).setdefault(candidate.supply_class, []).append(candidate)

    result: dict[str, dict[str, tuple[ResidentialSupplyCandidate, ...]]] = {}
    for parent, classes in mutable.items():
        result[parent] = {
            supply_class: tuple(sorted(rows, key=lambda row: row.candidate_id))
            for supply_class, rows in classes.items()
        }
    return result


def _select_candidate(
    household_id: str,
    parent_full14: str,
    pool: tuple[ResidentialSupplyCandidate, ...],
) -> tuple[ResidentialSupplyCandidate, str, float]:
    payload = f"{SELECTION_NAMESPACE}|{household_id}|{parent_full14}|SELECT".encode()
    digest = hashlib.sha256(payload).digest()
    digest_hex = digest.hex()
    unit = int.from_bytes(digest[:8], "big", signed=False) / float(1 << 64)
    total = sum(candidate.allocation_area_m2 for candidate in pool)
    if not math.isfinite(total) or total <= 0.0:
        raise ValueError(f"Invalid residential candidate pool mass for {parent_full14}")
    target = unit * total
    cumulative = 0.0
    for candidate in pool:
        cumulative += candidate.allocation_area_m2
        if target < cumulative:
            return candidate, digest_hex, total
    return pool[-1], digest_hex, total


def _fallback_point(
    household_id: str,
    candidate: ResidentialSupplyCandidate,
) -> tuple[Any, str, int | None]:
    shapely_geometry: Any = importlib.import_module("shapely.geometry")
    min_x, min_y, max_x, max_y = (
        float(value) for value in candidate.geometry_25833.bounds
    )
    width = max_x - min_x
    height = max_y - min_y
    if not math.isfinite(width) or not math.isfinite(height) or width <= 0.0 or height <= 0.0:
        point = candidate.geometry_25833.representative_point()
        return point, "FALLBACK_POINT_ON_SURFACE", None

    for attempt in range(FALLBACK_MAX_ATTEMPTS):
        payload = (
            f"{SELECTION_NAMESPACE}|{household_id}|{candidate.candidate_id}|POINT|{attempt}"
        ).encode()
        digest = hashlib.sha256(payload).digest()
        ux = int.from_bytes(digest[:8], "big", signed=False) / float(1 << 64)
        uy = int.from_bytes(digest[8:16], "big", signed=False) / float(1 << 64)
        point = shapely_geometry.Point(min_x + ux * width, min_y + uy * height)
        if candidate.geometry_25833.covers(point):
            return point, "HASH_REJECTION_UNIFORM_AREA", attempt

    point = candidate.geometry_25833.representative_point()
    return point, "FALLBACK_POINT_ON_SURFACE", None
