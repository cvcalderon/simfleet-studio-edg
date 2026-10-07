import gzip
import hashlib
from pathlib import Path

import pytest

from simfleet_edg.repro import f4_1c_c_materialize as runner

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "configs/f4/f4_1c_c_materialization_preopen_v1.yaml"


def test_deterministic_csv_gz_has_identical_bytes(tmp_path: Path) -> None:
    rows = [
        {"location_id": "osm:node:1", "level": "OSM_SUPPLY"},
        {"location_id": "osm:node:2", "level": "OSM_SUPPLY"},
    ]
    first = tmp_path / "a.csv.gz"
    second = tmp_path / "b.csv.gz"
    runner._write_csv_gz(first, ("location_id", "level"), iter(rows))
    runner._write_csv_gz(second, ("location_id", "level"), iter(rows))

    assert first.read_bytes() == second.read_bytes()
    assert hashlib.sha256(first.read_bytes()).hexdigest() == hashlib.sha256(
        second.read_bytes()
    ).hexdigest()
    assert gzip.decompress(first.read_bytes()).decode("utf-8") == (
        "location_id,level\nosm:node:1,OSM_SUPPLY\nosm:node:2,OSM_SUPPLY\n"
    )



def test_contract_hash_accepts_only_documented_csv_eol_normalization(tmp_path: Path) -> None:
    csv_path = tmp_path / "registry.csv"
    lf_bytes = b"rule_id,purpose\nR1,WORK_COMMUTE\n"
    crlf_bytes = lf_bytes.replace(b"\n", b"\r\n")
    expected = hashlib.sha256(crlf_bytes).hexdigest()

    csv_path.write_bytes(lf_bytes)
    assert runner._contract_hash_ok(csv_path, expected)

    csv_path.write_bytes(crlf_bytes)
    assert runner._contract_hash_ok(csv_path, expected)

    csv_path.write_bytes(b"rule_id,purpose\nR1,SHOPPING\n")
    assert not runner._contract_hash_ok(csv_path, expected)

def test_precheck_contract_and_boundaries_without_large_runtime_inputs(tmp_path: Path) -> None:
    result = runner.precheck(
        ROOT,
        CONFIG,
        tmp_path,
        check_environment=False,
        check_large_inputs=False,
    )
    assert result["status"] == "PASS", result["failed"]
    assert result["network_access"] == "NONE"


def test_official_execution_requires_real_git_clone(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError, match="real Git clone"):
        runner.require_frozen_implementation_commit(tmp_path)


def test_canonical_output_set_is_exactly_six_files() -> None:
    assert runner.OUTPUT_FILES == (
        "location_supply_v1.csv.gz",
        "location_supply_evidence_v1.csv.gz",
        "residential_supply_candidates_v1.csv.gz",
        "residential_anchors_v1.csv.gz",
        "residential_anchor_evidence_v1.csv.gz",
        "materialization_exclusions_v1.csv.gz",
    )
