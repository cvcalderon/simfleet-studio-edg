from pathlib import Path

from simfleet_edg.common.source_audit import sha256_file


def test_sha256_file(tmp_path: Path) -> None:
    path = tmp_path / "sample.bin"
    path.write_bytes(b"simfleet-studio-edg\n")
    assert sha256_file(path) == "c25996cd5875bc1f34b209e5724e6d52c868a88effd708cb6837b9f489b73964"


def test_r1_config_present() -> None:
    root = Path(__file__).resolve().parents[1]
    assert (root / "configs" / "reproduction" / "r1_source_audit.yaml").is_file()


def test_r1_config_uses_reproducible_official_glossary_hash() -> None:
    import yaml

    root = Path(__file__).resolve().parents[1]
    config = yaml.safe_load((root / "configs" / "reproduction" / "r1_source_audit.yaml").read_text())
    glossary = next(source for source in config["sources"] if source["source_id"] == "Z22_BERLIN_GLOSSARY")
    assert glossary["sha256"] == "a4f3e5884a3ba4966a29c63eede4f20844b6cc673da1dc06f975717926ee2bdf"
    assert glossary["superseded_local_copy_sha256"] == "ebd66160413268167b9962876aca4ff9bd46b7ea76eefb6e77955149b1662e4f"
