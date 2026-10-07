import json
from pathlib import Path

from simfleet_edg.spatial.location_supply import ResidentialSupplyCandidate
from simfleet_edg.spatial.lor_lookup import EXPECTED_M1_BEZIRK_IDS, FrozenLorLookup
from simfleet_edg.spatial.residential_anchor import (
    HouseholdHomeInput,
    realize_residential_anchors,
)


def _lookup(root: Path) -> FrozenLorLookup:
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


def _candidate(
    lookup: FrozenLorLookup,
    parent: str,
    index: int,
    supply_class: str = "RESIDENTIAL_BUILDING",
) -> ResidentialSupplyCandidate:
    geometry = lookup.borough(parent).geometry_25833
    area = float(geometry.area)
    code2d = parent[-2:]
    return ResidentialSupplyCandidate(
        candidate_id=f"rescand:way:{index}:bezirk:{code2d}",
        source_snapshot_id="OSM_GEOFABRIK_BERLIN_2026-10-04_V1",
        osm_element_type="way",
        osm_element_id=index,
        supply_class=supply_class,
        parent_m1_bezirk_id=parent,
        parent_bezirk_code_2d=code2d,
        source_area_m2=area,
        allocation_area_m2=area,
        pool_priority=1 if supply_class == "RESIDENTIAL_BUILDING" else 2,
        provenance="test",
        geometry_25833=geometry,
    )


def test_all_12_m1_parents_are_preserved_and_realization_is_deterministic(tmp_path: Path) -> None:
    lookup = _lookup(tmp_path)
    households = tuple(
        HouseholdHomeInput(f"HH_{index:02d}", "BEZIRK", parent)
        for index, parent in enumerate(EXPECTED_M1_BEZIRK_IDS, start=1)
    )
    candidates = tuple(
        _candidate(lookup, parent, index)
        for index, parent in enumerate(EXPECTED_M1_BEZIRK_IDS, start=1)
    )

    first = realize_residential_anchors(
        households=households,
        candidates=candidates,
        lor_lookup=lookup,
        source_snapshot_id="OSM_GEOFABRIK_BERLIN_2026-10-04_V1",
    )
    second = realize_residential_anchors(
        households=households,
        candidates=candidates,
        lor_lookup=lookup,
        source_snapshot_id="OSM_GEOFABRIK_BERLIN_2026-10-04_V1",
    )

    assert len(first.anchors) == 12
    assert first.fallback_household_count == 0
    assert first == second
    assert {anchor.parent_bezirk_id for anchor in first.anchors} == set(EXPECTED_M1_BEZIRK_IDS)
    for anchor, evidence in zip(first.anchors, first.evidence, strict=True):
        assert anchor.location.location_id == f"home:{anchor.household_id}"
        assert evidence.realized_plr_id[:2] == anchor.parent_bezirk_id[-2:]
        assert evidence.realized_lor_bzr_id[:2] == anchor.parent_bezirk_id[-2:]
        assert evidence.point_method == "POINT_ON_SURFACE"
        assert len(evidence.selection_hash_sha256) == 64


def test_landuse_fallback_uses_hash_keyed_point_when_building_pool_absent(tmp_path: Path) -> None:
    lookup = _lookup(tmp_path)
    parent = EXPECTED_M1_BEZIRK_IDS[0]
    household = HouseholdHomeInput("HH_FALLBACK", "BEZIRK", parent)
    fallback = _candidate(
        lookup,
        parent,
        900,
        supply_class="RESIDENTIAL_AREA_FALLBACK",
    )

    result = realize_residential_anchors(
        households=(household,),
        candidates=(fallback,),
        lor_lookup=lookup,
        source_snapshot_id="OSM_GEOFABRIK_BERLIN_2026-10-04_V1",
        require_all_frozen_boroughs=False,
    )

    assert result.fallback_household_count == 1
    assert result.evidence[0].pool_class_used == "AREA_FALLBACK"
    assert result.evidence[0].point_method == "HASH_REJECTION_UNIFORM_AREA"
    assert result.evidence[0].point_attempt_index is not None
