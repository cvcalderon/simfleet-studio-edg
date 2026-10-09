from __future__ import annotations

import json
from pathlib import Path

import pytest

from simfleet_edg.spatial.spatial_core_io import (
    load_frozen_supply,
    read_gz_rows,
    write_gzip_rows,
    write_json,
)


def _mini_supply(tmp_path: Path) -> None:
    write_gzip_rows(tmp_path / "location_supply_v1.csv.gz",
        ("location_id", "level", "lon", "lat", "crs", "eligible_purposes_json",
         "attractiveness", "capacity", "provenance"),
        [{"location_id": "poi", "level": "OSM_SUPPLY", "lon": 13.4, "lat": 52.5,
          "crs": "EPSG:4326", "eligible_purposes_json": json.dumps([
              "WORK_COMMUTE", "EDUCATION", "BUSINESS", "SHOPPING", "LEISURE", "OTHER"]),
          "attractiveness": "", "capacity": "", "provenance": "FROZEN"}])
    write_gzip_rows(tmp_path / "location_supply_evidence_v1.csv.gz",
        ("location_id", "plr_id", "geometry_kind", "projected_area_m2"),
        [{"location_id": "poi", "plr_id": "110010101", "geometry_kind": "POLYGON",
          "projected_area_m2": 123.}])
    write_gzip_rows(tmp_path / "residential_anchors_v1.csv.gz",
        ("household_id", "location_id", "level", "lon", "lat", "crs",
         "parent_bezirk_id", "provenance"),
        [{"household_id": "h", "location_id": "home", "level": "SYNTHETIC_HOME",
          "lon": 13.4, "lat": 52.5, "crs": "EPSG:4326",
          "parent_bezirk_id": "11000000000000", "provenance": "FROZEN"}])
    write_gzip_rows(tmp_path / "residential_anchor_evidence_v1.csv.gz",
        ("household_id",), [{"household_id": "h"}])


def test_minimal_canonical_only_reconstruction(tmp_path: Path) -> None:
    _mini_supply(tmp_path)
    data = load_frozen_supply(tmp_path, verify_hashes=False, expected_supply=1, expected_anchors=1)
    assert len(data.records) == 1
    assert set(data.indices) == {"WORK_COMMUTE", "EDUCATION", "BUSINESS", "SHOPPING", "LEISURE", "OTHER"}
    assert data.records[0].attractiveness is None
    assert data.records[0].capacity is None
    assert data.anchors["h"].location.location_id == "home"
    assert len(read_gz_rows(tmp_path / "location_supply_v1.csv.gz")) == 1


def test_reject_canonical_capacity_and_overwrites(tmp_path: Path) -> None:
    _mini_supply(tmp_path)
    path = tmp_path / "out.json"
    write_json(path, {"b": 2, "a": 1})
    assert path.read_text().startswith('{\n  "a"')
    with pytest.raises(FileExistsError):
        write_json(path, {"c": 3})
    with pytest.raises(FileExistsError):
        write_gzip_rows(tmp_path / "location_supply_v1.csv.gz", ("x",), [])
    with pytest.raises(ValueError, match="FROZEN_C_HASH_MISMATCH"):
        load_frozen_supply(tmp_path, verify_hashes=True, expected_supply=1, expected_anchors=1)
