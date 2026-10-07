import json
from pathlib import Path

from simfleet_edg.spatial.location_supply import materialize_location_supply
from simfleet_edg.spatial.lor_lookup import FrozenLorLookup
from simfleet_edg.spatial.osm_registry import EligibilityRegistry

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "docs/F4_1C_A3_OSM_TAG_TO_PURPOSE_ELIGIBILITY_REGISTRY_v1.csv"


def _write_lor_fixture(root: Path) -> FrozenLorLookup:
    layers: dict[str, list[dict[str, object]]] = {"plr": [], "bzr": [], "pgr": []}
    for index in range(1, 13):
        code = f"{index:02d}"
        x0 = 13.0 + index * 0.02
        x1 = x0 + 0.015
        polygon = {
            "type": "Polygon",
            "coordinates": [[[x0, 52.4], [x1, 52.4], [x1, 52.5], [x0, 52.5], [x0, 52.4]]],
        }
        pgr_id = f"{code}01"
        bzr_id = f"{code}0001"
        plr_id = f"{code}000101"
        layers["pgr"].append(
            {"type": "Feature", "properties": {"pgr_id": pgr_id}, "geometry": polygon}
        )
        layers["bzr"].append(
            {
                "type": "Feature",
                "properties": {"bzr_id": bzr_id, "pgr_id": pgr_id},
                "geometry": polygon,
            }
        )
        layers["plr"].append(
            {
                "type": "Feature",
                "properties": {"plr_id": plr_id, "bzr_id": bzr_id, "pgr_id": pgr_id},
                "geometry": polygon,
            }
        )

    paths: dict[str, Path] = {}
    for level, features in layers.items():
        path = root / f"{level}.geojson"
        path.write_text(
            json.dumps({"type": "FeatureCollection", "features": features}), encoding="utf-8"
        )
        paths[level] = path
    return FrozenLorLookup.from_geojson(
        plr_path=paths["plr"],
        bzr_path=paths["bzr"],
        pgr_path=paths["pgr"],
        enforce_frozen_counts=False,
    )


def _write_osm(path: Path) -> None:
    path.write_text(
        """<?xml version="1.0" encoding="UTF-8"?>
<osm version="0.6" generator="f4-c-test">
  <node id="1" lat="52.4500" lon="13.0250">
    <tag k="amenity" v="recycling"/><tag k="name" v="Depot A"/>
  </node>
  <node id="2" lat="52.4502" lon="13.0252">
    <tag k="amenity" v="recycling"/><tag k="name" v="Depot A"/>
  </node>
  <node id="3" lat="52.4510" lon="13.0260">
    <tag k="shop" v="books"/><tag k="capacity" v="12"/>
  </node>
  <node id="4" lat="52.4500" lon="14.0000"><tag k="shop" v="books"/></node>
  <node id="100" lat="52.4520" lon="13.0260"/>
  <node id="101" lat="52.4520" lon="13.0270"/>
  <node id="102" lat="52.4530" lon="13.0270"/>
  <node id="103" lat="52.4530" lon="13.0260"/>
  <way id="10">
    <nd ref="100"/><nd ref="101"/><nd ref="102"/><nd ref="103"/><nd ref="100"/>
    <tag k="building" v="apartments"/>
  </way>
  <node id="110" lat="52.4540" lon="13.0280"/>
  <node id="111" lat="52.4540" lon="13.0290"/>
  <node id="112" lat="52.4550" lon="13.0290"/>
  <node id="113" lat="52.4550" lon="13.0280"/>
  <way id="20">
    <nd ref="110"/><nd ref="111"/><nd ref="112"/><nd ref="113"/><nd ref="110"/>
    <tag k="landuse" v="residential"/>
  </way>
</osm>
""",
        encoding="utf-8",
    )


def test_materialization_keeps_physical_ids_separate_and_excludes_outside(tmp_path: Path) -> None:
    lookup = _write_lor_fixture(tmp_path)
    osm = tmp_path / "fixture.osm"
    _write_osm(osm)
    registry = EligibilityRegistry.from_csv(REGISTRY)

    result = materialize_location_supply(
        source_path=osm,
        registry=registry,
        extraction_keys=(
            "amenity",
            "building",
            "craft",
            "healthcare",
            "landuse",
            "leisure",
            "office",
            "shop",
            "historic",
            "tourism",
        ),
        lor_lookup=lookup,
        source_snapshot_id="OSM_GEOFABRIK_BERLIN_2026-10-04_V1",
    )

    identifiers = [row.location.location_id for row in result.records]
    assert identifiers == ["osm:node:1", "osm:node:2", "osm:node:3"]
    assert all(row.attractiveness is None and row.capacity is None for row in result.records)
    assert any(row.reason == "OUTSIDE_FROZEN_LOR" and row.osm_element_id == 4 for row in result.exclusions)

    evidence = {row.location_id: row for row in result.evidence}
    assert evidence["osm:node:1"].potential_duplicate_group_ids
    assert evidence["osm:node:1"].potential_duplicate_group_ids == evidence[
        "osm:node:2"
    ].potential_duplicate_group_ids
    assert evidence["osm:node:3"].osm_capacity_raw == "12"
    assert evidence["osm:node:3"].assignment.plr_id == "01000101"


def test_residential_candidates_are_clipped_to_m1_borough_and_keep_priority(tmp_path: Path) -> None:
    lookup = _write_lor_fixture(tmp_path)
    osm = tmp_path / "fixture.osm"
    _write_osm(osm)
    result = materialize_location_supply(
        source_path=osm,
        registry=EligibilityRegistry.from_csv(REGISTRY),
        extraction_keys=("building", "landuse", "shop", "amenity"),
        lor_lookup=lookup,
        source_snapshot_id="OSM_GEOFABRIK_BERLIN_2026-10-04_V1",
    )

    candidates = {row.candidate_id: row for row in result.residential_candidates}
    building = candidates["rescand:way:10:bezirk:01"]
    fallback = candidates["rescand:way:20:bezirk:01"]
    assert building.parent_m1_bezirk_id == "11000000000001"
    assert building.supply_class == "RESIDENTIAL_BUILDING"
    assert building.pool_priority == 1
    assert fallback.supply_class == "RESIDENTIAL_AREA_FALLBACK"
    assert fallback.pool_priority == 2
    assert building.allocation_area_m2 > 0.0
    assert fallback.allocation_area_m2 > 0.0
