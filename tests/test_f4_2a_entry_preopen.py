from __future__ import annotations

import hashlib
from pathlib import Path


def test_normative_bytewise_files_are_frozen() -> None:
    repo = Path(__file__).resolve().parents[1]
    frozen = {
        "docs/F4_2A_CORE_SPATIAL_CANDIDATE_DESIGN_FREEZE_v1.md":
            "9d5189aead090e1acfb5eb1a58cedaf57e10d9b8fd7a7c6e516147022a1ee382",
        "docs/F4_2A_MAIN_SCIENTIFIC_PREOPEN_SPEC_v1.yaml":
            "78ccb295c2388cf051e0af5f01daa0fbd6f3a782468f75171f51f302a1ad290b",
    }
    for path, expected in frozen.items():
        assert hashlib.sha256((repo / path).read_bytes()).hexdigest() == expected


def test_exact_26_new_paths_and_25_checksum_entries() -> None:
    repo = Path(__file__).resolve().parents[1]
    paths = (repo / "docs/F4_2A_OVERLAY_FILELIST_v1.txt").read_text().splitlines()
    assert len(paths) == len(set(paths)) == 26
    hashes = (repo / "docs/F4_2A_OVERLAY_CHECKSUMS_v1.sha256").read_text().splitlines()
    assert len(hashes) == 25
    for item in hashes:
        expected, path = item.split("  ", 1)
        assert path in paths
        assert hashlib.sha256((repo / path).read_bytes()).hexdigest() == expected
