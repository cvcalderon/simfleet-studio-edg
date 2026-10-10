"""Git safety, all eleven variants, and exact parent requirements."""
from __future__ import annotations

from pathlib import Path

import pytest

from simfleet_edg.repro import f4_2b_b_partial_integration as worker
from simfleet_edg.spatial.escort_day_binding import VARIANTS


def test_variant_registry_includes_all_originals_without_selection() -> None:
    assert len(VARIANTS) == len(set(VARIANTS)) == 11
    assert VARIANTS[0] == "B0_NO_LINK"
    assert VARIANTS[-1] == "B2_SRV2023_HH100"


def test_new_head_cannot_equal_prior_parent(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    values = {"symbolic-ref": "main", "rev-parse": worker.PARENT,
              "diff-tree": "", "status": ""}
    monkeypatch.setattr(worker, "_git", lambda repo, *args: values[args[0]])
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs/F4_2B_B_OVERLAY_FILELIST_v1.txt").write_text("x\n")
    with pytest.raises(RuntimeError, match="POSTPUSH_GIT_LINEAGE"):
        worker.git_gate(tmp_path)


def test_forbidden_test_cal_paths() -> None:
    for path in ("/tmp/MiD_TEST", "/tmp/CAL/foo", "/tmp/calibration"):
        with pytest.raises(ValueError, match="BLOCKED_FORBIDDEN"):
            worker.safe(Path(path))


def test_original_tar_member_bytes_are_bound_to_extracted_tree(tmp_path: Path) -> None:
    import tarfile

    output = tmp_path / "extracted"
    (output / "A").mkdir(parents=True)
    artifact = output / "A/file.txt"
    artifact.write_bytes(b"original immutable data\n")
    package = tmp_path / "official.tar.gz"
    with tarfile.open(package, "w:gz") as stream:
        stream.add(artifact, arcname="runbundle/A/file.txt")
    assert worker.verify_original_tar_tree(package, output) == 1
    artifact.write_bytes(b"altered\n")
    with pytest.raises(RuntimeError, match="BYTES_MISMATCH"):
        worker.verify_original_tar_tree(package, output)
