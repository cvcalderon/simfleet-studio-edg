from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from math import isfinite
from pathlib import Path
from typing import Any

SOURCE_CRS = "EPSG:4326"
METRIC_WORKING_CRS = "EPSG:25833"

LEVELS = {
    "PLR": {
        "id_field": "plr_id",
        "expected_count": 542,
        "parent_field": "bzr_id",
    },
    "BZR": {
        "id_field": "bzr_id",
        "expected_count": 143,
        "parent_field": "pgr_id",
    },
    "PGR": {
        "id_field": "pgr_id",
        "expected_count": 58,
        "parent_field": None,
    },
}


@dataclass(frozen=True, slots=True)
class LorLayerAudit:
    level: str
    feature_count: int
    unique_id_count: int
    missing_geometry_count: int
    empty_geometry_count: int
    invalid_geometry_count: int
    nonfinite_source_bounds_count: int
    nonfinite_projected_bounds_count: int
    nonpositive_projected_area_count: int
    source_crs: str
    metric_crs: str

    @property
    def passed(self) -> bool:
        expected = int(LEVELS[self.level]["expected_count"])
        return (
            self.feature_count == expected
            and self.unique_id_count == expected
            and self.missing_geometry_count == 0
            and self.empty_geometry_count == 0
            and self.invalid_geometry_count == 0
            and self.nonfinite_source_bounds_count == 0
            and self.nonfinite_projected_bounds_count == 0
            and self.nonpositive_projected_area_count == 0
        )

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["passed"] = self.passed
        return result


def _load_feature_collection(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("type") != "FeatureCollection":
        raise ValueError(f"Expected FeatureCollection: {path}")
    if not isinstance(data.get("features"), list):
        raise ValueError(f"Missing features list: {path}")
    return data


def _finite_bounds(bounds: tuple[float, float, float, float]) -> bool:
    return all(isfinite(float(value)) for value in bounds)


def audit_lor_layer(
    path: Path,
    level: str,
    *,
    source_crs: str = SOURCE_CRS,
    metric_crs: str = METRIC_WORKING_CRS,
) -> LorLayerAudit:
    try:
        from pyproj import Transformer
        from shapely.geometry import shape
        from shapely.ops import transform
    except ImportError as exc:
        raise RuntimeError(
            "F4.1b spatial environment requires the 'spatial' extra: "
            "python -m pip install -e '.[spatial]'"
        ) from exc

    if level not in LEVELS:
        raise ValueError(f"Unsupported LOR level: {level}")

    data = _load_feature_collection(path)
    features = data["features"]
    id_field = str(LEVELS[level]["id_field"])

    identifiers: list[str] = []
    missing = 0
    empty = 0
    invalid = 0
    nonfinite_source = 0
    nonfinite_projected = 0
    nonpositive_area = 0

    transformer = Transformer.from_crs(
        source_crs,
        metric_crs,
        always_xy=True,
    )

    for feature in features:
        properties = feature.get("properties") or {}
        identifier = properties.get(id_field)
        if identifier is None:
            raise ValueError(f"{level} feature without {id_field}")
        identifiers.append(str(identifier))

        raw_geometry = feature.get("geometry")
        if raw_geometry is None:
            missing += 1
            continue

        geometry = shape(raw_geometry)
        if geometry.is_empty:
            empty += 1
            continue
        if not geometry.is_valid:
            invalid += 1
        if not _finite_bounds(tuple(float(v) for v in geometry.bounds)):
            nonfinite_source += 1

        projected = transform(transformer.transform, geometry)
        if not _finite_bounds(tuple(float(v) for v in projected.bounds)):
            nonfinite_projected += 1
        if not isfinite(float(projected.area)) or projected.area <= 0:
            nonpositive_area += 1

    if len(identifiers) != len(set(identifiers)):
        duplicate_count = len(identifiers) - len(set(identifiers))
        raise ValueError(f"{level} contains {duplicate_count} duplicate IDs")

    return LorLayerAudit(
        level=level,
        feature_count=len(features),
        unique_id_count=len(set(identifiers)),
        missing_geometry_count=missing,
        empty_geometry_count=empty,
        invalid_geometry_count=invalid,
        nonfinite_source_bounds_count=nonfinite_source,
        nonfinite_projected_bounds_count=nonfinite_projected,
        nonpositive_projected_area_count=nonpositive_area,
        source_crs=source_crs,
        metric_crs=metric_crs,
    )


def _properties_by_id(path: Path, level: str) -> dict[str, dict[str, Any]]:
    data = _load_feature_collection(path)
    id_field = str(LEVELS[level]["id_field"])
    result: dict[str, dict[str, Any]] = {}
    for feature in data["features"]:
        properties = dict(feature.get("properties") or {})
        identifier = str(properties[id_field])
        if identifier in result:
            raise ValueError(f"Duplicate {level} ID: {identifier}")
        result[identifier] = properties
    return result


def audit_lor_hierarchy(plr_path: Path, bzr_path: Path, pgr_path: Path) -> dict[str, Any]:
    plr = _properties_by_id(plr_path, "PLR")
    bzr = _properties_by_id(bzr_path, "BZR")
    pgr = _properties_by_id(pgr_path, "PGR")

    missing_bzr = sorted(
        identifier
        for identifier, properties in plr.items()
        if str(properties.get("bzr_id")) not in bzr
    )
    missing_pgr = sorted(
        identifier
        for identifier, properties in bzr.items()
        if str(properties.get("pgr_id")) not in pgr
    )

    inconsistent_plr_bzr: list[str] = []
    for identifier, properties in plr.items():
        parent = bzr.get(str(properties.get("bzr_id")))
        if parent is None:
            continue
        if str(properties.get("pgr_id")) != str(parent.get("pgr_id")):
            inconsistent_plr_bzr.append(identifier)
            continue
        if str(properties.get("bez")) != str(parent.get("bez")):
            inconsistent_plr_bzr.append(identifier)

    inconsistent_bzr_pgr: list[str] = []
    for identifier, properties in bzr.items():
        parent = pgr.get(str(properties.get("pgr_id")))
        if parent is None:
            continue
        if str(properties.get("bez")) != str(parent.get("bez")):
            inconsistent_bzr_pgr.append(identifier)

    passed = not (
        missing_bzr
        or missing_pgr
        or inconsistent_plr_bzr
        or inconsistent_bzr_pgr
    )

    return {
        "passed": passed,
        "plr_count": len(plr),
        "bzr_count": len(bzr),
        "pgr_count": len(pgr),
        "missing_bzr_for_plr": missing_bzr,
        "missing_pgr_for_bzr": missing_pgr,
        "inconsistent_plr_bzr": inconsistent_plr_bzr,
        "inconsistent_bzr_pgr": inconsistent_bzr_pgr,
    }


def audit_all_lor(
    plr_path: Path,
    bzr_path: Path,
    pgr_path: Path,
) -> dict[str, Any]:
    layers = {
        "PLR": audit_lor_layer(plr_path, "PLR").to_dict(),
        "BZR": audit_lor_layer(bzr_path, "BZR").to_dict(),
        "PGR": audit_lor_layer(pgr_path, "PGR").to_dict(),
    }
    hierarchy = audit_lor_hierarchy(plr_path, bzr_path, pgr_path)
    return {
        "source_crs": SOURCE_CRS,
        "metric_working_crs": METRIC_WORKING_CRS,
        "layers": layers,
        "hierarchy": hierarchy,
        "passed": all(layer["passed"] for layer in layers.values())
        and bool(hierarchy["passed"]),
    }
