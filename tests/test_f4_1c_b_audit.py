import json
from pathlib import Path

from shapely.geometry import Polygon

from simfleet_edg.spatial.osm_audit import RawOsmFeature, _audit_point, audit_osm_supply
from simfleet_edg.spatial.osm_registry import EligibilityRegistry

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "docs/F4_1C_A3_OSM_TAG_TO_PURPOSE_ELIGIBILITY_REGISTRY_v1.csv"


def _write_lor(path: Path, level: str, identifier: str) -> None:
    id_field = "bzr_id" if level == "BZR" else "plr_id"
    payload = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {id_field: identifier},
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [
                        [
                            [13.39, 52.49],
                            [13.43, 52.49],
                            [13.43, 52.53],
                            [13.39, 52.53],
                            [13.39, 52.49],
                        ]
                    ],
                },
            }
        ],
    }
    path.write_text(json.dumps(payload), encoding="utf-8")


def _write_osm(path: Path) -> None:
    path.write_text(
        """<?xml version="1.0" encoding="UTF-8"?>
<osm version="0.6" generator="f4-test">
  <node id="1" lat="52.5000" lon="13.4000">
    <tag k="amenity" v="recycling"/><tag k="name" v="Depot A"/><tag k="capacity" v="20"/>
  </node>
  <node id="2" lat="52.5002" lon="13.4002">
    <tag k="amenity" v="recycling"/><tag k="name" v="Depot A"/>
  </node>
  <node id="3" lat="52.5004" lon="13.4004"><tag k="shop" v="vacant"/></node>
  <node id="100" lat="52.5010" lon="13.4010"/>
  <node id="101" lat="52.5010" lon="13.4020"/>
  <node id="102" lat="52.5020" lon="13.4020"/>
  <node id="103" lat="52.5020" lon="13.4010"/>
  <way id="10">
    <nd ref="100"/><nd ref="101"/><nd ref="102"/><nd ref="103"/><nd ref="100"/>
    <tag k="building" v="school"/><tag k="capacity" v="100"/><tag k="building:levels" v="3"/>
  </way>
  <node id="110" lat="52.5030" lon="13.4030"/>
  <node id="111" lat="52.5030" lon="13.4040"/>
  <node id="112" lat="52.5040" lon="13.4040"/>
  <node id="113" lat="52.5040" lon="13.4030"/>
  <way id="20">
    <nd ref="110"/><nd ref="111"/><nd ref="112"/><nd ref="113"/><nd ref="110"/>
    <tag k="building" v="apartments"/>
  </way>
  <node id="120" lat="52.5050" lon="13.4050"/>
  <node id="121" lat="52.5060" lon="13.4060"/>
  <node id="122" lat="52.5050" lon="13.4060"/>
  <node id="123" lat="52.5060" lon="13.4050"/>
  <way id="30">
    <nd ref="120"/><nd ref="121"/><nd ref="122"/><nd ref="123"/><nd ref="120"/>
    <tag k="building" v="school"/>
  </way>
</osm>
""",
        encoding="utf-8",
    )


def test_audit_is_evidence_only_and_produces_lor_support(tmp_path: Path) -> None:
    osm = tmp_path / "fixture.osm"
    bzr = tmp_path / "bzr.geojson"
    plr = tmp_path / "plr.geojson"
    _write_osm(osm)
    _write_lor(bzr, "BZR", "BZR-X")
    _write_lor(plr, "PLR", "PLR-X")
    registry = EligibilityRegistry.from_csv(REGISTRY)
    result = audit_osm_supply(
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
        bzr_path=bzr,
        plr_path=plr,
    )

    purpose_rows = result.tables["purpose_supply_counts.csv"]
    purpose_counts = {row["purpose"]: row["eligible_record_count"] for row in purpose_rows}
    assert purpose_counts["OTHER"] == 2
    assert purpose_counts["EDUCATION"] == 1
    assert purpose_counts["WORK_COMMUTE"] == 3

    capacity_rows = result.tables["a4_capacity_like_raw_audit.csv"]
    assert any(row["field"] == "capacity" and row["raw_value"] == "100" for row in capacity_rows)
    assert all(row["promoted_to_capacity"] == "NO" for row in capacity_rows)

    area_rows = result.tables["a4_area_evidence_audit.csv"]
    assert area_rows
    assert all(row["canonical_capacity_written"] == "NO" for row in area_rows)
    assert all(row["canonical_attractiveness_written"] == "NO" for row in area_rows)

    residential = result.tables["residential_support_by_bzr_plr.csv"]
    assert any(row["level"] == "BZR" and row["zone_id"] == "BZR-X" for row in residential)
    assert any(row["level"] == "PLR" and row["zone_id"] == "PLR-X" for row in residential)

    nonhome = result.tables["nonhome_support_by_bzr_plr.csv"]
    assert any(row["level"] == "BZR" and row["zone_id"] == "BZR-X" for row in nonhome)
    assert any(row["level"] == "PLR" and row["zone_id"] == "PLR-X" for row in nonhome)

    duplicate_rows = result.tables["potential_duplicate_audit.csv"]
    assert any(row["normalized_identity"] == "depot a" for row in duplicate_rows)
    assert all(row["destructive_merge"] == "NO" for row in duplicate_rows)

    geometry = result.tables["geometry_quality_audit.csv"]
    assert any(row["status"] == "INVALID_EXCLUDED" for row in geometry)


def test_polygon_audit_point_uses_point_on_surface() -> None:
    polygon = Polygon([(0, 0), (3, 0), (3, 1), (1, 1), (1, 3), (0, 3), (0, 0)])
    feature = RawOsmFeature(
        element_type="way",
        element_id=1,
        geometry_kind="POLYGON",
        tags={"leisure": "park"},
        geometry=polygon,
        geometry_valid=True,
    )
    point = _audit_point(feature)
    assert point is not None
    assert polygon.covers(point)


def test_missing_capacity_does_not_remove_eligibility(tmp_path: Path) -> None:
    osm = tmp_path / "single.osm"
    osm.write_text(
        '<osm version="0.6"><node id="1" lat="52.5" lon="13.4"><tag k="shop" v="books"/></node></osm>',
        encoding="utf-8",
    )
    bzr = tmp_path / "bzr.geojson"
    plr = tmp_path / "plr.geojson"
    _write_lor(bzr, "BZR", "BZR-X")
    _write_lor(plr, "PLR", "PLR-X")
    result = audit_osm_supply(
        source_path=osm,
        registry=EligibilityRegistry.from_csv(REGISTRY),
        extraction_keys=("shop",),
        bzr_path=bzr,
        plr_path=plr,
    )
    assert result.metrics["eligible_valid_records"] == 1
    assert result.tables["a4_capacity_like_raw_audit.csv"] == []
