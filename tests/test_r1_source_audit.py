from pathlib import Path

from simfleet_edg.common.source_audit import sha256_file


def test_sha256_file(tmp_path: Path) -> None:
    path = tmp_path / "sample.bin"
    path.write_bytes(b"simfleet-studio-edg\n")
    assert sha256_file(path) == "c25996cd5875bc1f34b209e5724e6d52c868a88effd708cb6837b9f489b73964"


def test_r1_config_present() -> None:
    root = Path(__file__).resolve().parents[1]
    assert (root / "configs" / "reproduction" / "r1_source_audit.yaml").is_file()
