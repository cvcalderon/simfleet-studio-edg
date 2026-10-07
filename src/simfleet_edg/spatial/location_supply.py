from __future__ import annotations

import hashlib
import json
import math
import re
from collections import defaultdict
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Final

from simfleet_edg.canonical.mobility import LocationRef, LocationSupplyRecord
from simfleet_edg.spatial.lor_lookup import FrozenLorLookup, LorAssignment, m1_bezirk_code2d
from simfleet_edg.spatial.osm_audit import RawOsmFeature, iter_osm_features
from simfleet_edg.spatial.osm_registry import EligibilityRegistry, RegistryDecision

SOURCE_CRS: Final[str] = "EPSG:4326"
METRIC_CRS: Final[str] = "EPSG:25833"
LOCATION_LEVEL: Final[str] = "OSM_SUPPLY"
DUPLICATE_POLICY: Final[str] = "KEEP_SEPARATE"
RESIDENTIAL_CLASSES: Final[tuple[str, str]] = (
    "RESIDENTIAL_BUILDING",
    "RESIDENTIAL_AREA_FALLBACK",
)

CsvScalar = str | int | float | None
CsvRow = dict[str, CsvScalar]


@dataclass(frozen=True, slots=True)
class LocationSupplyEvidence:
    location_id: str
    source_snapshot_id: str
    osm_element_type: str
    osm_element_id: int
    supply_classes: tuple[str, ...]
    supply_tier: str
    a3_rule_ids: tuple[str, ...]
    matched_tags: dict[str, str]
    geometry_kind: str
    representative_point_method: str
    projected_area_m2: float | None
    osm_capacity_raw: str | None
    building_levels_raw: str | None
    assignment: LorAssignment
    potential_duplicate_group_ids: tuple[str, ...]
    provenance: str

    def to_row(self) -> CsvRow:
        return {
            "location_id": self.location_id,
            "source_snapshot_id": self.source_snapshot_id,
            "osm_element_type": self.osm_element_type,
            "osm_element_id": self.osm_element_id,
            "supply_classes_json": _json_array(self.supply_classes),
            "supply_tier": self.supply_tier,
            "a3_rule_ids_json": _json_array(self.a3_rule_ids),
            "matched_tags_json": _json_object(self.matched_tags),
            "geometry_kind": self.geometry_kind,
            "representative_point_method": self.representative_point_method,
            "projected_area_m2": self.projected_area_m2,
            "osm_capacity_raw": self.osm_capacity_raw,
            "building_levels_raw": self.building_levels_raw,
            "plr_id": self.assignment.plr_id,
            "lor_bzr_id": self.assignment.lor_bzr_id,
            "pgr_id": self.assignment.pgr_id,
            "potential_duplicate_group_ids_json": _json_array(
                self.potential_duplicate_group_ids
            ),
            "duplicate_policy": DUPLICATE_POLICY,
            "provenance": self.provenance,
        }


@dataclass(frozen=True, slots=True)
class ResidentialSupplyCandidate:
    candidate_id: str
    source_snapshot_id: str
    osm_element_type: str
    osm_element_id: int
    supply_class: str
    parent_m1_bezirk_id: str
    parent_bezirk_code_2d: str
    source_area_m2: float
    allocation_area_m2: float
    pool_priority: int
    provenance: str
    geometry_25833: Any

    def to_row(self) -> CsvRow:
        return {
            "candidate_id": self.candidate_id,
            "source_snapshot_id": self.source_snapshot_id,
            "osm_element_type": self.osm_element_type,
            "osm_element_id": self.osm_element_id,
            "supply_class": self.supply_class,
            "parent_m1_bezirk_id": self.parent_m1_bezirk_id,
            "parent_bezirk_code_2d": self.parent_bezirk_code_2d,
            "source_area_m2": self.source_area_m2,
            "allocation_area_m2": self.allocation_area_m2,
            "pool_priority": self.pool_priority,
            "provenance": self.provenance,
        }


@dataclass(frozen=True, slots=True)
class MaterializationExclusion:
    osm_element_type: str
    osm_element_id: int
    reason: str
    detail: dict[str, str | int | float | bool | None]
    provenance: str

    def to_row(self) -> CsvRow:
        return {
            "osm_element_type": self.osm_element_type,
            "osm_element_id": self.osm_element_id,
            "reason": self.reason,
            "detail_json": _json_object(self.detail),
            "provenance": self.provenance,
        }


@dataclass(frozen=True, slots=True)
class LocationSupplyMaterialization:
    records: tuple[LocationSupplyRecord, ...]
    evidence: tuple[LocationSupplyEvidence, ...]
    residential_candidates: tuple[ResidentialSupplyCandidate, ...]
    exclusions: tuple[MaterializationExclusion, ...]

    def purpose_label_counts(self) -> dict[str, int]:
        counts: defaultdict[str, int] = defaultdict(int)
        for record in self.records:
            for purpose in record.eligible_purposes:
                counts[purpose] += 1
        return dict(sorted(counts.items()))


def materialize_location_supply(
    *,
    source_path: Path,
    registry: EligibilityRegistry,
    extraction_keys: tuple[str, ...],
    lor_lookup: FrozenLorLookup,
    source_snapshot_id: str,
) -> LocationSupplyMaterialization:
    records: list[LocationSupplyRecord] = []
    evidence: list[LocationSupplyEvidence] = []
    candidates: list[ResidentialSupplyCandidate] = []
    exclusions: list[MaterializationExclusion] = []
    duplicate_identity: list[tuple[str, str | None, str | None, tuple[str, ...]]] = []
    provenance = f"F4.1c-C|{source_snapshot_id}|DESIGN_V2"

    for feature in iter_osm_features(source_path):
        decision = registry.evaluate(feature.tags, feature.geometry_kind)
        if not decision.admitted:
            continue
        if not feature.geometry_valid or feature.geometry is None:
            exclusions.append(
                MaterializationExclusion(
                    osm_element_type=feature.element_type,
                    osm_element_id=feature.element_id,
                    reason="INVALID_ELIGIBLE_GEOMETRY",
                    detail={"geometry_kind": feature.geometry_kind},
                    provenance=provenance,
                )
            )
            continue

        metric_geometry: Any | None = None
        projected_area: float | None = None
        if feature.geometry_kind == "POLYGON":
            metric_geometry = lor_lookup.to_metric_geometry(feature.geometry)
            projected_area = float(metric_geometry.area)
            if not math.isfinite(projected_area) or projected_area <= 0.0:
                exclusions.append(
                    MaterializationExclusion(
                        osm_element_type=feature.element_type,
                        osm_element_id=feature.element_id,
                        reason="NONPOSITIVE_PROJECTED_AREA",
                        detail={},
                        provenance=provenance,
                    )
                )
                continue

        if decision.eligible_purposes:
            point, method = _representative_point(
                feature,
                metric_geometry=metric_geometry,
                lor_lookup=lor_lookup,
            )
            if point is None:
                exclusions.append(
                    MaterializationExclusion(
                        osm_element_type=feature.element_type,
                        osm_element_id=feature.element_id,
                        reason="NO_OPERATIONAL_REPRESENTATIVE_POINT",
                        detail={"geometry_kind": feature.geometry_kind},
                        provenance=provenance,
                    )
                )
            else:
                assignment = lor_lookup.locate(float(point.x), float(point.y))
                if assignment is None:
                    exclusions.append(
                        MaterializationExclusion(
                            osm_element_type=feature.element_type,
                            osm_element_id=feature.element_id,
                            reason="OUTSIDE_FROZEN_LOR",
                            detail={
                                "eligible_purposes": ";".join(decision.eligible_purposes)
                            },
                            provenance=provenance,
                        )
                    )
                else:
                    location_id = f"osm:{feature.element_type}:{feature.element_id}"
                    location = LocationRef(
                        location_id=location_id,
                        level=LOCATION_LEVEL,
                        lon=float(point.x),
                        lat=float(point.y),
                        crs=SOURCE_CRS,
                    )
                    record = LocationSupplyRecord(
                        location=location,
                        eligible_purposes=decision.eligible_purposes,
                        attractiveness=None,
                        capacity=None,
                        provenance=provenance,
                    )
                    records.append(record)
                    evidence.append(
                        LocationSupplyEvidence(
                            location_id=location_id,
                            source_snapshot_id=source_snapshot_id,
                            osm_element_type=feature.element_type,
                            osm_element_id=feature.element_id,
                            supply_classes=decision.supply_classes,
                            supply_tier=(
                                "AREA_FALLBACK" if decision.area_fallback else "EXPLICIT"
                            ),
                            a3_rule_ids=decision.include_rule_ids,
                            matched_tags=_matched_tags(feature.tags, extraction_keys),
                            geometry_kind=feature.geometry_kind,
                            representative_point_method=method,
                            projected_area_m2=projected_area,
                            osm_capacity_raw=feature.tags.get("capacity"),
                            building_levels_raw=feature.tags.get("building:levels"),
                            assignment=assignment,
                            potential_duplicate_group_ids=(),
                            provenance=provenance,
                        )
                    )
                    duplicate_identity.append(
                        (
                            location_id,
                            _normalize_identity(feature.tags.get("name")),
                            _normalized_address(feature.tags),
                            decision.eligible_purposes,
                        )
                    )

        if decision.residential_support and feature.geometry_kind == "POLYGON":
            if metric_geometry is None:
                raise AssertionError("Residential polygon must have projected geometry")
            supply_class = _residential_supply_class(decision)
            if supply_class is None:
                raise ValueError(
                    "A3 admitted residential support without a frozen residential supply class"
                )
            fragments = lor_lookup.intersecting_borough_fragments(metric_geometry)
            if not fragments:
                exclusions.append(
                    MaterializationExclusion(
                        osm_element_type=feature.element_type,
                        osm_element_id=feature.element_id,
                        reason="RESIDENTIAL_OUTSIDE_M1_BOROUGH_UNIONS",
                        detail={"supply_class": supply_class},
                        provenance=provenance,
                    )
                )
            for parent_full14, fragment in fragments:
                allocation_area = float(fragment.area)
                if not math.isfinite(allocation_area) or allocation_area <= 0.0:
                    continue
                code2d = m1_bezirk_code2d(parent_full14)
                candidates.append(
                    ResidentialSupplyCandidate(
                        candidate_id=(
                            f"rescand:{feature.element_type}:{feature.element_id}:bezirk:{code2d}"
                        ),
                        source_snapshot_id=source_snapshot_id,
                        osm_element_type=feature.element_type,
                        osm_element_id=feature.element_id,
                        supply_class=supply_class,
                        parent_m1_bezirk_id=parent_full14,
                        parent_bezirk_code_2d=code2d,
                        source_area_m2=float(metric_geometry.area),
                        allocation_area_m2=allocation_area,
                        pool_priority=1 if supply_class == "RESIDENTIAL_BUILDING" else 2,
                        provenance=provenance,
                        geometry_25833=fragment,
                    )
                )

    _validate_unique_records(records)
    _validate_unique_candidates(candidates)
    duplicate_groups = _duplicate_group_memberships(duplicate_identity)
    evidence = [
        replace(
            row,
            potential_duplicate_group_ids=tuple(
                sorted(duplicate_groups.get(row.location_id, set()))
            ),
        )
        for row in evidence
    ]

    records.sort(key=lambda row: row.location.location_id)
    evidence.sort(key=lambda row: row.location_id)
    candidates.sort(key=lambda row: row.candidate_id)
    exclusions.sort(key=lambda row: (row.reason, row.osm_element_type, row.osm_element_id))
    return LocationSupplyMaterialization(
        records=tuple(records),
        evidence=tuple(evidence),
        residential_candidates=tuple(candidates),
        exclusions=tuple(exclusions),
    )


def location_supply_row(record: LocationSupplyRecord) -> CsvRow:
    return {
        "location_id": record.location.location_id,
        "level": record.location.level,
        "lon": record.location.lon,
        "lat": record.location.lat,
        "crs": record.location.crs,
        "eligible_purposes_json": _json_array(record.eligible_purposes),
        "attractiveness": record.attractiveness,
        "capacity": record.capacity,
        "provenance": record.provenance,
    }


def _representative_point(
    feature: RawOsmFeature,
    *,
    metric_geometry: Any | None,
    lor_lookup: FrozenLorLookup,
) -> tuple[Any | None, str]:
    if feature.geometry_kind == "POINT":
        return feature.geometry, "NODE_COORDINATE"
    if feature.geometry_kind == "POLYGON" and metric_geometry is not None:
        point_25833 = metric_geometry.representative_point()
        point_4326 = lor_lookup.to_source_geometry(point_25833)
        return point_4326, "POINT_ON_SURFACE"
    return None, "NONE"


def _residential_supply_class(decision: RegistryDecision) -> str | None:
    classes = set(decision.supply_classes)
    if "RESIDENTIAL_BUILDING" in classes:
        return "RESIDENTIAL_BUILDING"
    if "RESIDENTIAL_AREA_FALLBACK" in classes:
        return "RESIDENTIAL_AREA_FALLBACK"
    return None


def _matched_tags(tags: dict[str, str], extraction_keys: tuple[str, ...]) -> dict[str, str]:
    frozen = set(extraction_keys)
    selected: dict[str, str] = {}
    for key, value in tags.items():
        if (
            key in frozen
            or key == "name"
            or key == "addr:full"
            or key.startswith("addr:")
            or key == "capacity"
            or key.startswith("capacity:")
            or key == "building:levels"
        ):
            selected[key] = value
    return dict(sorted(selected.items()))


def _normalize_identity(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = re.sub(r"[^a-z0-9]+", " ", value.casefold()).strip()
    return normalized or None


def _normalized_address(tags: dict[str, str]) -> str | None:
    if tags.get("addr:full"):
        return _normalize_identity(tags["addr:full"])
    parts = [
        tags.get("addr:street"),
        tags.get("addr:housenumber"),
        tags.get("addr:postcode"),
        tags.get("addr:city"),
    ]
    present = [part for part in parts if part]
    return _normalize_identity(" ".join(present)) if present else None


def _duplicate_group_memberships(
    rows: list[tuple[str, str | None, str | None, tuple[str, ...]]],
) -> dict[str, set[str]]:
    groups: defaultdict[tuple[str, str, str], set[str]] = defaultdict(set)
    for location_id, normalized_name, normalized_address, purposes in rows:
        for purpose in purposes:
            if normalized_name:
                groups[("NAME", normalized_name, purpose)].add(location_id)
            if normalized_address:
                groups[("ADDRESS", normalized_address, purpose)].add(location_id)

    memberships: defaultdict[str, set[str]] = defaultdict(set)
    for key, members in sorted(groups.items()):
        if len(members) < 2:
            continue
        raw = "|".join(key).encode("utf-8")
        digest = hashlib.sha256(raw).hexdigest()[:24]
        group_id = f"dup:{key[0].lower()}:{digest}"
        for location_id in members:
            memberships[location_id].add(group_id)
    return dict(memberships)


def _validate_unique_records(records: list[LocationSupplyRecord]) -> None:
    identifiers = [record.location.location_id for record in records]
    if len(identifiers) != len(set(identifiers)):
        raise ValueError("Duplicate canonical LocationSupplyRecord location_id")


def _validate_unique_candidates(candidates: list[ResidentialSupplyCandidate]) -> None:
    identifiers = [candidate.candidate_id for candidate in candidates]
    if len(identifiers) != len(set(identifiers)):
        raise ValueError("Duplicate residential candidate_id")


def _json_array(values: tuple[str, ...]) -> str:
    return json.dumps(list(values), ensure_ascii=False, separators=(",", ":"))


def _json_object(values: dict[str, Any]) -> str:
    return json.dumps(values, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
