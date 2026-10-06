from pathlib import Path

from simfleet_edg.spatial.lor import (
    METRIC_WORKING_CRS,
    SOURCE_CRS,
    audit_all_lor,
)

ROOT = Path(__file__).resolve().parents[1]

PLR = ROOT / "data/raw/lor/lor_2021_a_lor_plr_2021_WGS84.geojson"
BZR = ROOT / "data/raw/lor/lor_2021_b_lor_bzr_2021_WGS84.geojson"
PGR = ROOT / "data/raw/lor/lor_2021_c_lor_pgr_2021_WGS84.geojson"


def test_crs_contract():
    assert SOURCE_CRS == "EPSG:4326"
    assert METRIC_WORKING_CRS == "EPSG:25833"


def test_lor_environment_gate():
    result = audit_all_lor(PLR, BZR, PGR)
    assert result["passed"] is True
    assert result["layers"]["PLR"]["feature_count"] == 542
    assert result["layers"]["BZR"]["feature_count"] == 143
    assert result["layers"]["PGR"]["feature_count"] == 58
    assert result["hierarchy"]["passed"] is True
