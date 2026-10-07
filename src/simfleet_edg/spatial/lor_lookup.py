from __future__ import annotations

import importlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final, cast

SOURCE_CRS: Final[str] = "EPSG:4326"
METRIC_CRS: Final[str] = "EPSG:25833"
EXPECTED_M1_BEZIRK_IDS: Final[tuple[str, ...]] = tuple(
    f"110000000000{index:02d}" for index in range(1, 13)
)
EXPECTED_BZR_COUNT: Final[int] = 143
EXPECTED_PLR_COUNT: Final[int] = 542
EXPECTED_PGR_COUNT: Final[int] = 58


@dataclass(frozen=True, slots=True)
class LorAssignment:
    plr_id: str
    lor_bzr_id: str
    pgr_id: str


@dataclass(frozen=True, slots=True)
class M1BezirkGeometry:
    full14_id: str
    code2d: str
    geometry_25833: Any


def validate_m1_bezirk_id(value: str) -> str:
    text = str(value)
    if text not in EXPECTED_M1_BEZIRK_IDS:
        raise ValueError(f"Invalid frozen M1 BEZIRK id: {value!r}")
    return text


def m1_bezirk_code2d(value: str) -> str:
    return validate_m1_bezirk_id(value)[-2:]


class FrozenLorLookup:
    def __init__(
        self,
        *,
        plr_geometries: list[Any],
        plr_ids: list[str],
        plr_to_bzr: dict[str, str],
        plr_to_pgr: dict[str, str],
        bzr_geometries: list[Any],
        bzr_ids: list[str],
        pgr_ids: set[str],
        enforce_frozen_counts: bool = True,
    ) -> None:
        if len(plr_geometries) != len(plr_ids):
            raise ValueError("PLR geometry/id length mismatch")
        if len(bzr_geometries) != len(bzr_ids):
            raise ValueError("BZR geometry/id length mismatch")
        if len(plr_ids) != len(set(plr_ids)):
            raise ValueError("Duplicate PLR IDs")
        if len(bzr_ids) != len(set(bzr_ids)):
            raise ValueError("Duplicate BZR IDs")
        if enforce_frozen_counts:
            observed = (len(plr_ids), len(bzr_ids), len(pgr_ids))
            expected = (EXPECTED_PLR_COUNT, EXPECTED_BZR_COUNT, EXPECTED_PGR_COUNT)
            if observed != expected:
                raise ValueError(f"Frozen LOR cardinality mismatch: {observed} != {expected}")

        prefixes = {f"{index:02d}" for index in range(1, 13)}
        if {identifier[:2] for identifier in bzr_ids} != prefixes:
            raise ValueError("Frozen LOR BZR must partition into prefixes 01..12")
        if not {identifier[:2] for identifier in plr_ids}.issubset(prefixes):
            raise ValueError("Frozen LOR PLR contains a prefix outside 01..12")
        if set(plr_to_bzr) != set(plr_ids) or set(plr_to_pgr) != set(plr_ids):
            raise ValueError("Incomplete PLR parent hierarchy")

        for plr_id in plr_ids:
            bzr_id = plr_to_bzr[plr_id]
            pgr_id = plr_to_pgr[plr_id]
            if bzr_id not in set(bzr_ids):
                raise ValueError(f"Unknown BZR parent for PLR {plr_id}: {bzr_id}")
            if pgr_id not in pgr_ids:
                raise ValueError(f"Unknown PGR parent for PLR {plr_id}: {pgr_id}")
            if plr_id[:2] != bzr_id[:2]:
                raise ValueError(f"PLR/BZR district prefix mismatch: {plr_id} -> {bzr_id}")

        shapely_strtree: Any = importlib.import_module("shapely.strtree")
        pyproj: Any = importlib.import_module("pyproj")
        shapely_ops: Any = importlib.import_module("shapely.ops")

        self._plr_geometries = plr_geometries
        self._plr_ids = plr_ids
        self._plr_to_bzr = plr_to_bzr
        self._plr_to_pgr = plr_to_pgr
        self._plr_tree = shapely_strtree.STRtree(plr_geometries)
        self._to_metric = pyproj.Transformer.from_crs(SOURCE_CRS, METRIC_CRS, always_xy=True)
        self._to_source = pyproj.Transformer.from_crs(METRIC_CRS, SOURCE_CRS, always_xy=True)

        grouped: dict[str, list[Any]] = {prefix: [] for prefix in sorted(prefixes)}
        for identifier, geometry in zip(bzr_ids, bzr_geometries, strict=True):
            projected = shapely_ops.transform(self._to_metric.transform, geometry)
            grouped[identifier[:2]].append(projected)

        self._boroughs: dict[str, M1BezirkGeometry] = {}
        borough_geometries: list[Any] = []
        self._borough_codes: list[str] = []
        for code2d, geometries in sorted(grouped.items()):
            if not geometries:
                raise ValueError(f"Empty frozen LOR BZR group for M1 borough {code2d}")
            union = shapely_ops.unary_union(geometries)
            if union.is_empty or not union.is_valid or float(union.area) <= 0.0:
                raise ValueError(f"Invalid M1 borough union for district {code2d}")
            full14 = f"110000000000{code2d}"
            borough = M1BezirkGeometry(full14, code2d, union)
            self._boroughs[full14] = borough
            self._borough_codes.append(code2d)
            borough_geometries.append(union)
        if tuple(sorted(self._boroughs)) != EXPECTED_M1_BEZIRK_IDS:
            raise ValueError("M1 borough bridge did not produce exactly the 12 frozen IDs")
        self._borough_geometries = borough_geometries
        self._borough_tree = shapely_strtree.STRtree(borough_geometries)

    @classmethod
    def from_geojson(
        cls,
        *,
        plr_path: Path,
        bzr_path: Path,
        pgr_path: Path,
        enforce_frozen_counts: bool = True,
    ) -> FrozenLorLookup:
        shapely_geometry: Any = importlib.import_module("shapely.geometry")
        plr_payload = _load_feature_collection(plr_path)
        bzr_payload = _load_feature_collection(bzr_path)
        pgr_payload = _load_feature_collection(pgr_path)

        plr_geometries: list[Any] = []
        plr_ids: list[str] = []
        plr_to_bzr: dict[str, str] = {}
        plr_to_pgr: dict[str, str] = {}
        for feature in plr_payload["features"]:
            properties = feature.get("properties") or {}
            plr_id = _required_property(properties, "plr_id", "PLR")
            bzr_id = _required_property(properties, "bzr_id", "PLR")
            pgr_id = _required_property(properties, "pgr_id", "PLR")
            geometry = _valid_geometry(shapely_geometry, feature, "PLR", plr_id)
            plr_geometries.append(geometry)
            plr_ids.append(plr_id)
            plr_to_bzr[plr_id] = bzr_id
            plr_to_pgr[plr_id] = pgr_id

        bzr_geometries: list[Any] = []
        bzr_ids: list[str] = []
        bzr_to_pgr: dict[str, str] = {}
        for feature in bzr_payload["features"]:
            properties = feature.get("properties") or {}
            bzr_id = _required_property(properties, "bzr_id", "BZR")
            pgr_id = _required_property(properties, "pgr_id", "BZR")
            geometry = _valid_geometry(shapely_geometry, feature, "BZR", bzr_id)
            bzr_geometries.append(geometry)
            bzr_ids.append(bzr_id)
            bzr_to_pgr[bzr_id] = pgr_id

        pgr_ids: set[str] = set()
        for feature in pgr_payload["features"]:
            properties = feature.get("properties") or {}
            pgr_id = _required_property(properties, "pgr_id", "PGR")
            _valid_geometry(shapely_geometry, feature, "PGR", pgr_id)
            if pgr_id in pgr_ids:
                raise ValueError(f"Duplicate PGR ID: {pgr_id}")
            pgr_ids.add(pgr_id)

        for plr_id, bzr_id in plr_to_bzr.items():
            if bzr_id not in bzr_to_pgr:
                raise ValueError(f"Unknown BZR parent for PLR {plr_id}: {bzr_id}")
            if plr_to_pgr[plr_id] != bzr_to_pgr[bzr_id]:
                raise ValueError(f"Inconsistent PLR/BZR/PGR hierarchy for {plr_id}")

        return cls(
            plr_geometries=plr_geometries,
            plr_ids=plr_ids,
            plr_to_bzr=plr_to_bzr,
            plr_to_pgr=plr_to_pgr,
            bzr_geometries=bzr_geometries,
            bzr_ids=bzr_ids,
            pgr_ids=pgr_ids,
            enforce_frozen_counts=enforce_frozen_counts,
        )

    @property
    def plr_count(self) -> int:
        return len(self._plr_ids)

    @property
    def borough_count(self) -> int:
        return len(self._boroughs)

    def borough(self, full14_id: str) -> M1BezirkGeometry:
        validated = validate_m1_bezirk_id(full14_id)
        return self._boroughs[validated]

    def to_metric_geometry(self, geometry_4326: Any) -> Any:
        shapely_ops: Any = importlib.import_module("shapely.ops")
        return shapely_ops.transform(self._to_metric.transform, geometry_4326)

    def to_source_geometry(self, geometry_25833: Any) -> Any:
        shapely_ops: Any = importlib.import_module("shapely.ops")
        return shapely_ops.transform(self._to_source.transform, geometry_25833)

    def locate(self, lon: float, lat: float) -> LorAssignment | None:
        shapely_geometry: Any = importlib.import_module("shapely.geometry")
        return self.locate_point(shapely_geometry.Point(float(lon), float(lat)))

    def locate_point(self, point_4326: Any) -> LorAssignment | None:
        matches: list[str] = []
        for raw_index in self._plr_tree.query(point_4326):
            index = int(raw_index)
            if self._plr_geometries[index].covers(point_4326):
                matches.append(self._plr_ids[index])
        if not matches:
            return None
        plr_id = sorted(matches)[0]
        return LorAssignment(
            plr_id=plr_id,
            lor_bzr_id=self._plr_to_bzr[plr_id],
            pgr_id=self._plr_to_pgr[plr_id],
        )

    def intersecting_borough_fragments(self, geometry_25833: Any) -> list[tuple[str, Any]]:
        fragments: list[tuple[str, Any]] = []
        for raw_index in self._borough_tree.query(geometry_25833):
            index = int(raw_index)
            borough_geometry = self._borough_geometries[index]
            intersection = geometry_25833.intersection(borough_geometry)
            if intersection.is_empty:
                continue
            area = float(intersection.area)
            if area <= 0.0:
                continue
            code2d = self._borough_codes[index]
            fragments.append((f"110000000000{code2d}", intersection))
        return sorted(fragments, key=lambda item: item[0])


def _load_feature_collection(path: Path) -> dict[str, Any]:
    payload = cast(dict[str, Any], json.loads(path.read_text(encoding="utf-8")))
    if payload.get("type") != "FeatureCollection" or not isinstance(payload.get("features"), list):
        raise ValueError(f"Expected GeoJSON FeatureCollection: {path}")
    return payload


def _required_property(properties: dict[str, Any], key: str, level: str) -> str:
    value = properties.get(key)
    if value is None or str(value) == "":
        raise ValueError(f"{level} feature missing {key}")
    return str(value)


def _valid_geometry(shapely_geometry: Any, feature: dict[str, Any], level: str, identifier: str) -> Any:
    raw = feature.get("geometry")
    if raw is None:
        raise ValueError(f"{level} {identifier} missing geometry")
    geometry = shapely_geometry.shape(raw)
    if geometry.is_empty or not geometry.is_valid:
        raise ValueError(f"Invalid frozen {level} geometry: {identifier}")
    return geometry
