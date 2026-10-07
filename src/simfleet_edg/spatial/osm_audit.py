from __future__ import annotations

import csv
import importlib
import json
import math
import re
import statistics
import time
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from simfleet_edg.spatial.osm_registry import EligibilityRegistry, RegistryDecision

SOURCE_CRS = "EPSG:4326"
METRIC_CRS = "EPSG:25833"
type CsvValue = str | int | float | None
type CsvRow = dict[str, CsvValue]


@dataclass(frozen=True, slots=True)
class RawOsmFeature:
    element_type: str
    element_id: int
    geometry_kind: str
    tags: dict[str, str]
    geometry: Any | None
    geometry_valid: bool


@dataclass(frozen=True, slots=True)
class DuplicateCandidate:
    element_type: str
    element_id: int
    normalized_name: str | None
    normalized_address: str | None
    semantic_buckets: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class AuditResult:
    tables: dict[str, list[CsvRow]]
    metrics: dict[str, CsvValue]
    summary_markdown: str

    def write(self, output: Path) -> None:
        output.mkdir(parents=True, exist_ok=True)
        for filename, rows in self.tables.items():
            _write_csv(output / filename, rows)
        (output / "F4_1C_B_AUDIT_SUMMARY.md").write_text(
            self.summary_markdown,
            encoding="utf-8",
        )


class LorIndex:
    def __init__(self, level: str, geometries: list[Any], identifiers: list[str]) -> None:
        if len(geometries) != len(identifiers):
            raise ValueError("LOR geometry/identifier length mismatch")
        shapely_strtree: Any = importlib.import_module("shapely.strtree")
        self.level = level
        self.geometries = geometries
        self.identifiers = identifiers
        self.tree = shapely_strtree.STRtree(geometries)

    @classmethod
    def from_geojson(cls, path: Path, level: str, id_field: str) -> LorIndex:
        shapely_geometry: Any = importlib.import_module("shapely.geometry")
        payload = json.loads(path.read_text(encoding="utf-8"))
        if payload.get("type") != "FeatureCollection":
            raise ValueError(f"Expected LOR FeatureCollection: {path}")
        geometries: list[Any] = []
        identifiers: list[str] = []
        for feature in payload.get("features", []):
            properties = feature.get("properties") or {}
            identifier = properties.get(id_field)
            raw_geometry = feature.get("geometry")
            if identifier is None or raw_geometry is None:
                raise ValueError(f"Malformed {level} LOR feature")
            geometry = shapely_geometry.shape(raw_geometry)
            if geometry.is_empty or not geometry.is_valid:
                raise ValueError(f"Invalid frozen {level} geometry")
            geometries.append(geometry)
            identifiers.append(str(identifier))
        return cls(level, geometries, identifiers)

    def locate(self, lon: float, lat: float) -> str | None:
        shapely_geometry: Any = importlib.import_module("shapely.geometry")
        point = shapely_geometry.Point(lon, lat)
        matches: list[str] = []
        for raw_index in self.tree.query(point):
            index = int(raw_index)
            if self.geometries[index].covers(point):
                matches.append(self.identifiers[index])
        return sorted(matches)[0] if matches else None


def iter_osm_features(path: Path) -> Iterator[RawOsmFeature]:
    lower = path.name.lower()
    if lower.endswith((".osm", ".xml", ".osm.xml")):
        yield from _iter_osm_xml_features(path)
        return
    yield from _iter_pbf_features(path)


def _iter_osm_xml_features(path: Path) -> Iterator[RawOsmFeature]:
    shapely_geometry: Any = importlib.import_module("shapely.geometry")
    root = ET.parse(path).getroot()
    nodes: dict[int, tuple[float, float]] = {}
    node_elements: list[ET.Element] = []
    way_elements: list[ET.Element] = []

    for child in root:
        if child.tag == "node":
            identifier = int(child.attrib["id"])
            lon = float(child.attrib["lon"])
            lat = float(child.attrib["lat"])
            nodes[identifier] = (lon, lat)
            node_elements.append(child)
        elif child.tag == "way":
            way_elements.append(child)

    for element in node_elements:
        tags = _xml_tags(element)
        if not tags:
            continue
        lon = float(element.attrib["lon"])
        lat = float(element.attrib["lat"])
        finite = math.isfinite(lon) and math.isfinite(lat)
        geometry = shapely_geometry.Point(lon, lat) if finite else None
        yield RawOsmFeature(
            element_type="node",
            element_id=int(element.attrib["id"]),
            geometry_kind="POINT",
            tags=tags,
            geometry=geometry,
            geometry_valid=finite,
        )

    for element in way_elements:
        tags = _xml_tags(element)
        if not tags:
            continue
        refs = [int(node.attrib["ref"]) for node in element.findall("nd")]
        closed = len(refs) >= 4 and refs[0] == refs[-1]
        coordinates = [nodes[ref] for ref in refs if ref in nodes]
        complete = len(coordinates) == len(refs)
        if closed and complete:
            geometry = shapely_geometry.Polygon(coordinates)
            valid = not geometry.is_empty and bool(geometry.is_valid)
            yield RawOsmFeature(
                element_type="way",
                element_id=int(element.attrib["id"]),
                geometry_kind="POLYGON",
                tags=tags,
                geometry=geometry,
                geometry_valid=valid,
            )
        else:
            yield RawOsmFeature(
                element_type="way",
                element_id=int(element.attrib["id"]),
                geometry_kind="LINE",
                tags=tags,
                geometry=None,
                geometry_valid=False,
            )


def _xml_tags(element: ET.Element) -> dict[str, str]:
    return {
        tag.attrib["k"]: tag.attrib["v"]
        for tag in element.findall("tag")
        if "k" in tag.attrib and "v" in tag.attrib
    }


def _iter_pbf_features(path: Path) -> Iterator[RawOsmFeature]:
    try:
        osmium: Any = importlib.import_module("osmium")
    except ImportError as exc:
        raise RuntimeError(
            "F4.1c-B PBF parsing requires the 'osm' extra: "
            "python -m pip install -e '.[osm]'"
        ) from exc
    shapely_geometry: Any = importlib.import_module("shapely.geometry")
    factory = osmium.geom.GeoJSONFactory()
    processor = osmium.FileProcessor(str(path)).with_areas()

    for obj in processor:
        tags = {tag.k: tag.v for tag in obj.tags}
        if not tags:
            continue
        if obj.is_node():
            valid = bool(obj.location.valid())
            geometry = (
                shapely_geometry.Point(float(obj.location.lon), float(obj.location.lat))
                if valid
                else None
            )
            yield RawOsmFeature(
                element_type="node",
                element_id=int(obj.id),
                geometry_kind="POINT",
                tags=tags,
                geometry=geometry,
                geometry_valid=valid,
            )
            continue
        if obj.is_area():
            try:
                raw_geojson = factory.create_multipolygon(obj)
                geometry = shapely_geometry.shape(json.loads(raw_geojson))
                valid = not geometry.is_empty and bool(geometry.is_valid)
            except Exception:
                geometry = None
                valid = False
            yield RawOsmFeature(
                element_type="way" if obj.from_way() else "relation",
                element_id=int(obj.orig_id()),
                geometry_kind="POLYGON",
                tags=tags,
                geometry=geometry,
                geometry_valid=valid,
            )
            continue
        if obj.is_way():
            if obj.ends_have_same_id():
                # Closed ways are represented once through the Area object.
                continue
            yield RawOsmFeature(
                element_type="way",
                element_id=int(obj.id),
                geometry_kind="LINE",
                tags=tags,
                geometry=None,
                geometry_valid=False,
            )
            continue
        if obj.is_relation() and tags.get("type") not in {"multipolygon", "boundary"}:
            yield RawOsmFeature(
                element_type="relation",
                element_id=int(obj.id),
                geometry_kind="RELATION",
                tags=tags,
                geometry=None,
                geometry_valid=False,
            )


def audit_osm_supply(
    *,
    source_path: Path,
    registry: EligibilityRegistry,
    extraction_keys: Iterable[str],
    bzr_path: Path,
    plr_path: Path,
) -> AuditResult:
    shapely_ops: Any = importlib.import_module("shapely.ops")
    pyproj: Any = importlib.import_module("pyproj")
    transformer = pyproj.Transformer.from_crs(SOURCE_CRS, METRIC_CRS, always_xy=True)
    bzr_index = LorIndex.from_geojson(bzr_path, "BZR", "bzr_id")
    plr_index = LorIndex.from_geojson(plr_path, "PLR", "plr_id")
    key_universe = frozenset(extraction_keys)

    key_values: Counter[tuple[str, str]] = Counter()
    rules: Counter[str] = Counter()
    unmapped: Counter[tuple[str, str]] = Counter()
    purposes: Counter[str] = Counter()
    geometry_quality: Counter[tuple[str, str]] = Counter()
    facility_split: Counter[tuple[str, str]] = Counter()
    support: Counter[tuple[str, str, str, str]] = Counter()
    area_values: defaultdict[tuple[str, str], list[float]] = defaultdict(list)
    capacity_values: Counter[tuple[str, str, str]] = Counter()
    duplicate_candidates: list[DuplicateCandidate] = []

    processed = 0
    relevant = 0
    effective = 0
    excluded = 0
    default_denied = 0
    invalid_eligible_geometry = 0
    start = time.perf_counter()

    for feature in iter_osm_features(source_path):
        processed += 1
        if not _is_relevant(feature.tags, key_universe):
            continue
        relevant += 1
        for key, value in feature.tags.items():
            if key in key_universe:
                key_values[(key, value)] += 1

        decision = registry.evaluate(feature.tags, feature.geometry_kind)
        for rule_id in decision.matched_rule_ids:
            rules[rule_id] += 1
        if decision.excluded:
            excluded += 1
        if decision.unmapped_default_deny:
            default_denied += 1
            for key, value in feature.tags.items():
                if key in key_universe:
                    unmapped[(key, value)] += 1

        if not decision.admitted:
            continue
        if not feature.geometry_valid or feature.geometry is None:
            invalid_eligible_geometry += 1
            geometry_quality[(feature.geometry_kind, "INVALID_EXCLUDED")] += 1
            continue

        point = _audit_point(feature)
        if point is None or not (math.isfinite(float(point.x)) and math.isfinite(float(point.y))):
            invalid_eligible_geometry += 1
            geometry_quality[(feature.geometry_kind, "NONFINITE_EXCLUDED")] += 1
            continue

        effective += 1
        geometry_quality[(feature.geometry_kind, "VALID")] += 1
        for purpose in decision.eligible_purposes:
            purposes[purpose] += 1

        supply_class = decision.primary_supply_class or "UNCLASSIFIED"
        split = "AREA_FALLBACK" if decision.area_fallback else "EXPLICIT_OR_BUILDING"
        facility_split[(supply_class, split)] += 1

        area_m2: float | None = None
        if feature.geometry_kind == "POLYGON":
            projected = shapely_ops.transform(transformer.transform, feature.geometry)
            if math.isfinite(float(projected.area)) and projected.area > 0:
                area_m2 = float(projected.area)
                buckets = decision.eligible_purposes or (
                    ("RESIDENTIAL",) if decision.residential_support else ()
                )
                for purpose in buckets:
                    area_values[(supply_class, purpose)].append(area_m2)
            else:
                geometry_quality[(feature.geometry_kind, "NONPOSITIVE_PROJECTED_AREA")] += 1

        _record_capacity_like(capacity_values, feature.tags, supply_class)
        _record_support(
            support,
            bzr_index,
            plr_index,
            point,
            decision,
            supply_class,
        )
        duplicate_candidates.append(_duplicate_candidate(feature, decision))

    duration = time.perf_counter() - start
    tables: dict[str, list[CsvRow]] = {
        "osm_key_value_inventory.csv": _counter_rows(
            key_values, ("osm_key", "osm_value"), "count"
        ),
        "a3_rule_application_counts.csv": _rule_rows(registry, rules),
        "unmapped_default_deny_inventory.csv": _counter_rows(
            unmapped, ("osm_key", "osm_value"), "count"
        ),
        "purpose_supply_counts.csv": [
            {"purpose": purpose, "eligible_record_count": count}
            for purpose, count in sorted(purposes.items())
        ],
        "geometry_quality_audit.csv": [
            {"geometry_kind": kind, "status": status, "count": count}
            for (kind, status), count in sorted(geometry_quality.items())
        ],
        "facility_vs_fallback_audit.csv": [
            {"supply_class": supply, "classification": split, "count": count}
            for (supply, split), count in sorted(facility_split.items())
        ],
        "potential_duplicate_audit.csv": _duplicate_rows(duplicate_candidates),
        "a4_area_evidence_audit.csv": _area_rows(area_values),
        "a4_capacity_like_raw_audit.csv": [
            {
                "supply_class": supply,
                "field": field,
                "raw_value": value,
                "count": count,
                "parseable_numeric": _parseable_number(value),
                "promoted_to_capacity": "NO",
            }
            for (supply, field, value), count in sorted(capacity_values.items())
        ],
        "residential_support_by_bzr_plr.csv": _support_rows(support, residential=True),
        "nonhome_support_by_bzr_plr.csv": _support_rows(support, residential=False),
        "performance.csv": [
            {"metric": "objects_seen", "value": processed},
            {"metric": "relevant_objects", "value": relevant},
            {"metric": "eligible_valid_records", "value": effective},
            {"metric": "excluded_objects", "value": excluded},
            {"metric": "default_denied_objects", "value": default_denied},
            {"metric": "invalid_eligible_geometry", "value": invalid_eligible_geometry},
            {"metric": "elapsed_seconds", "value": round(duration, 6)},
        ],
    }
    metrics: dict[str, CsvValue] = {
        "objects_seen": processed,
        "relevant_objects": relevant,
        "eligible_valid_records": effective,
        "excluded_objects": excluded,
        "default_denied_objects": default_denied,
        "invalid_eligible_geometry": invalid_eligible_geometry,
        "elapsed_seconds": round(duration, 6),
    }
    summary = _summary(metrics, purposes, area_values, tables["potential_duplicate_audit.csv"])
    return AuditResult(tables=tables, metrics=metrics, summary_markdown=summary)


def _is_relevant(tags: dict[str, str], key_universe: frozenset[str]) -> bool:
    lifecycle = ("disused:", "abandoned:", "demolished:", "razed:", "removed:", "proposed:", "construction:")
    return any(key in key_universe or key.startswith(lifecycle) for key in tags)


def _audit_point(feature: RawOsmFeature) -> Any | None:
    if feature.geometry is None:
        return None
    if feature.geometry_kind == "POINT":
        return feature.geometry
    if feature.geometry_kind == "POLYGON":
        # Shapely representative_point() implements point-on-surface semantics.
        return feature.geometry.representative_point()
    return None


def _record_capacity_like(
    counter: Counter[tuple[str, str, str]],
    tags: dict[str, str],
    supply_class: str,
) -> None:
    for key, value in tags.items():
        if key == "capacity" or key.startswith("capacity:") or key == "building:levels":
            counter[(supply_class, key, value)] += 1


def _record_support(
    counter: Counter[tuple[str, str, str, str]],
    bzr_index: LorIndex,
    plr_index: LorIndex,
    point: Any,
    decision: RegistryDecision,
    supply_class: str,
) -> None:
    lon = float(point.x)
    lat = float(point.y)
    zones = {"BZR": bzr_index.locate(lon, lat), "PLR": plr_index.locate(lon, lat)}
    if decision.residential_support:
        for level, zone in zones.items():
            counter[("RESIDENTIAL", level, zone or "OUTSIDE", supply_class)] += 1
    for purpose in decision.eligible_purposes:
        for level, zone in zones.items():
            counter[("NONHOME", level, zone or "OUTSIDE", purpose)] += 1


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


def _duplicate_candidate(
    feature: RawOsmFeature,
    decision: RegistryDecision,
) -> DuplicateCandidate:
    buckets = decision.eligible_purposes
    if decision.residential_support:
        buckets = (*buckets, "RESIDENTIAL")
    return DuplicateCandidate(
        element_type=feature.element_type,
        element_id=feature.element_id,
        normalized_name=_normalize_identity(feature.tags.get("name")),
        normalized_address=_normalized_address(feature.tags),
        semantic_buckets=tuple(sorted(set(buckets))),
    )


def _duplicate_rows(candidates: list[DuplicateCandidate]) -> list[CsvRow]:
    groups: defaultdict[tuple[str, str, str], list[DuplicateCandidate]] = defaultdict(list)
    for candidate in candidates:
        for semantic in candidate.semantic_buckets:
            if candidate.normalized_name:
                groups[("NAME", candidate.normalized_name, semantic)].append(candidate)
            if candidate.normalized_address:
                groups[("ADDRESS", candidate.normalized_address, semantic)].append(candidate)

    rows: list[CsvRow] = []
    for (evidence, identity, semantic), members in sorted(groups.items()):
        unique = {(member.element_type, member.element_id) for member in members}
        if len(unique) < 2:
            continue
        count = len(unique)
        sample = ";".join(f"{kind}/{identifier}" for kind, identifier in sorted(unique)[:8])
        rows.append(
            {
                "evidence_type": evidence,
                "normalized_identity": identity,
                "semantic_bucket": semantic,
                "member_count": count,
                "potential_pair_count": count * (count - 1) // 2,
                "sample_members": sample,
                "destructive_merge": "NO",
            }
        )
    return rows


def _area_rows(values: defaultdict[tuple[str, str], list[float]]) -> list[CsvRow]:
    rows: list[CsvRow] = []
    for (supply, purpose), observations in sorted(values.items()):
        ordered = sorted(observations)
        rows.append(
            {
                "supply_class": supply,
                "purpose": purpose,
                "polygon_count": len(ordered),
                "area_min_m2": round(ordered[0], 3),
                "area_p50_m2": round(_percentile(ordered, 0.50), 3),
                "area_p90_m2": round(_percentile(ordered, 0.90), 3),
                "area_mean_m2": round(statistics.fmean(ordered), 3),
                "area_max_m2": round(ordered[-1], 3),
                "canonical_attractiveness_written": "NO",
                "canonical_capacity_written": "NO",
            }
        )
    return rows


def _percentile(ordered: list[float], q: float) -> float:
    if not ordered:
        raise ValueError("Cannot compute percentile of empty data")
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * q
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    weight = position - lower
    return ordered[lower] * (1.0 - weight) + ordered[upper] * weight


def _parseable_number(value: str) -> str:
    try:
        number = float(value)
    except ValueError:
        return "NO"
    return "YES" if math.isfinite(number) else "NO"


def _support_rows(
    counter: Counter[tuple[str, str, str, str]], *, residential: bool
) -> list[CsvRow]:
    target = "RESIDENTIAL" if residential else "NONHOME"
    rows: list[CsvRow] = []
    for (kind, level, zone, semantic), count in sorted(counter.items()):
        if kind != target:
            continue
        rows.append(
            {
                "level": level,
                "zone_id": zone,
                "supply_class" if residential else "purpose": semantic,
                "eligible_record_count": count,
            }
        )
    return rows


def _counter_rows(
    counter: Counter[tuple[str, str]],
    dimensions: tuple[str, str],
    count_name: str,
) -> list[CsvRow]:
    return [
        {dimensions[0]: key[0], dimensions[1]: key[1], count_name: count}
        for key, count in sorted(counter.items())
    ]


def _rule_rows(registry: EligibilityRegistry, counts: Counter[str]) -> list[CsvRow]:
    return [
        {
            "rule_id": rule.rule_id,
            "priority": rule.priority,
            "decision": rule.decision,
            "application_count": counts[rule.rule_id],
        }
        for rule in registry.rules
        if rule.rule_kind not in {"PURPOSE_GUARD", "DEFAULT_DENY"}
    ]


def _write_csv(path: Path, rows: list[CsvRow]) -> None:
    if rows:
        fieldnames = list(rows[0])
    else:
        fieldnames = ["status"]
        rows = [{"status": "NO_ROWS"}]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="raise")
        writer.writeheader()
        writer.writerows(rows)


def _summary(
    metrics: dict[str, CsvValue],
    purposes: Counter[str],
    areas: defaultdict[tuple[str, str], list[float]],
    duplicate_rows: list[CsvRow],
) -> str:
    lines = [
        "# F4.1c-B OSM Supply Evidence Audit Summary",
        "",
        "**Mode:** audit only — no operational location assignment or candidate scoring.",
        "",
        "## Processing",
        "",
        f"- OSM objects seen: `{metrics['objects_seen']}`",
        f"- Relevant tagged objects: `{metrics['relevant_objects']}`",
        f"- Eligible records with valid audit geometry: `{metrics['eligible_valid_records']}`",
        f"- Explicitly excluded objects: `{metrics['excluded_objects']}`",
        f"- Default-denied objects: `{metrics['default_denied_objects']}`",
        f"- Invalid eligible geometry excluded: `{metrics['invalid_eligible_geometry']}`",
        "",
        "## Eligible non-home supply by purpose",
        "",
    ]
    if purposes:
        for purpose, count in sorted(purposes.items()):
            lines.append(f"- {purpose}: `{count}`")
    else:
        lines.append("- No eligible non-home records observed.")
    lines.extend(
        [
            "",
            "## A4 raw evidence",
            "",
            f"- Supply/purpose groups with projected-area evidence: `{len(areas)}`",
            "- Projected area is retained only as raw evidence; it is not converted to people capacity or canonical attractiveness.",
            "",
            "## Duplicate diagnostics",
            "",
            f"- Strong-identity potential duplicate groups: `{len(duplicate_rows)}`",
            "- Potential duplicates are preserved and flagged; no destructive merge is performed.",
            "",
            "## Boundary",
            "",
            "No `LocationSupplyRecord`, final `ResidentialAnchor`, household assignment, activity-destination assignment, S_NEAR, S_DIST, S_ATTR, G3 CAL, or G3 TEST output is produced by this audit.",
            "",
        ]
    )
    return "\n".join(lines)
