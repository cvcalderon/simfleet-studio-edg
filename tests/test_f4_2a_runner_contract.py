from pathlib import Path

import pytest

from simfleet_edg.repro.f4_2a_core_spatial import (
    M1_FILES,
    PARENT,
    SCENARIO_ID,
    postpush_gate,
    read_m1,
)


def test_no_smoke_approved_as_official_full_population(tmp_path: Path) -> None:
    assert len(M1_FILES) == 3
    assert SCENARIO_ID == "F4_2A_CORE_REFERENCE_V1"
    assert PARENT.startswith("61f29671")
    with pytest.raises(RuntimeError, match="M1_HASH_BLOCKED"):
        read_m1(tmp_path)


def test_postpush_rejects_directory_without_git(tmp_path: Path) -> None:
    with pytest.raises(Exception):
        postpush_gate(tmp_path)
