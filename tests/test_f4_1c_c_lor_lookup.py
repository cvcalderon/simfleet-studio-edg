import json
from pathlib import Path

import pytest

from simfleet_edg.spatial.lor_lookup import (
    EXPECTED_M1_BEZIRK_IDS,
    FrozenLorLookup,
    m1_bezirk_code2d,
    validate_m1_bezirk_id,
)


def _write_lor_fixture(root: Path) -> tuple[Path, Path, Path]:
    plr_features = []
    bzr_features = []
    pgr_features = []
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
        pgr_features.append(
            {"type": "Feature", "properties": {"pgr_id": pgr_id}, "geometry": polygon}
        )
        bzr_features.append(
            {
                "type": "Feature",
                "properties": {"bzr_id": bzr_id, "pgr_id": pgr_id},
                "geometry": polygon,
            }
        )
        plr_features.append(
            {
                "type": "Feature",
                "properties": {"plr_id": plr_id, "bzr_id": bzr_id, "pgr_id": pgr_id},
                "geometry": polygon,
            }
        )

    paths = []
    for name, features in (
        ("plr.geojson", plr_features),
        ("bzr.geojson", bzr_features),
        ("pgr.geojson", pgr_features),
    ):
        path = root / name
        path.write_text(
            json.dumps({"type": "FeatureCollection", "features": features}), encoding="utf-8"
        )
        paths.append(path)
    return paths[0], paths[1], paths[2]


def test_m1_bezirk_is_12_full14_ids_not_lor_bzr() -> None:
    assert len(EXPECTED_M1_BEZIRK_IDS) == 12
    assert EXPECTED_M1_BEZIRK_IDS[0] == "11000000000001"
    assert EXPECTED_M1_BEZIRK_IDS[-1] == "11000000000012"
    assert m1_bezirk_code2d("11000000000007") == "07"
    with pytest.raises(ValueError):
        validate_m1_bezirk_id("070001")


def test_lor_bridge_builds_12_borough_unions_and_resolves_hierarchy(tmp_path: Path) -> None:
    plr, bzr, pgr = _write_lor_fixture(tmp_path)
    lookup = FrozenLorLookup.from_geojson(
        plr_path=plr,
        bzr_path=bzr,
        pgr_path=pgr,
        enforce_frozen_counts=False,
    )

    assert lookup.borough_count == 12
    assert lookup.plr_count == 12
    borough = lookup.borough("11000000000001")
    assert borough.code2d == "01"
    assert borough.geometry_25833.area > 0.0

    assignment = lookup.locate(13.027, 52.45)
    assert assignment is not None
    assert assignment.plr_id == "01000101"
    assert assignment.lor_bzr_id == "010001"
    assert assignment.pgr_id == "0101"

    fragments = lookup.intersecting_borough_fragments(borough.geometry_25833)
    assert [parent for parent, _ in fragments] == ["11000000000001"]
