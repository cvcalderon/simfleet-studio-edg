from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path
from typing import Any

import pytest

from simfleet_edg.repro.f4_2b_a_local_sensitivity import (
    PROPOSAL_COLUMNS,
    _verified_git_lineage,
    _verify_overlay_bytes,
    safe_path,
)
from simfleet_edg.spatial.escort_synthetic_relations import load_variants


def test_run_contract_and_no_extras() -> None:
    root = Path(__file__).resolve().parents[1]
    allowed = (root / "docs/F4_2B_A_LOCAL_OVERLAY_FILELIST_v1.txt").read_text().splitlines()
    assert len(allowed) == 20 and len(set(allowed)) == 20
    assert "target_person_id" in PROPOSAL_COLUMNS
    assert "household_size_class" in PROPOSAL_COLUMNS
    assert "resource_state" in PROPOSAL_COLUMNS
    assert "mode" not in PROPOSAL_COLUMNS
    rows = load_variants(root / "docs/F4_2B_A_LOCAL_VARIANT_MATRIX_v1.csv")
    assert len(rows) == 10
    assert [(v.year, v.p_household) for v in rows][:2] == [("2018", 0.0), ("2018", .25)]


def test_frozen_filename_and_forbidden_data(tmp_path: Path) -> None:
    p = tmp_path / "input"
    assert safe_path(p) == p.absolute()
    with pytest.raises(ValueError, match="Forbidden"):
        safe_path(tmp_path / "MiD_TEST/secret.csv")


# The lineage tests use actual Git commits; the official gate does not mock Git.


_FROZEN_EOL = (
    "docs/F4_2B_A_LOCAL_VARIANT_MATRIX_v1.csv",
    "docs/F4_2B_A_LOCAL_VALIDATION_GATES_v1.csv",
)
_MANIFEST = "docs/F4_2B_A_LOCAL_OVERLAY_CHECKSUMS_v1.sha256"


def _real_git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=repo, check=True, capture_output=True, text=True
    )
    return result.stdout.strip()


def _write_overlay_manifest(repo: Path, items: list[str]) -> None:
    entries = []
    for rel in items:
        if rel == _MANIFEST:
            continue
        data = (repo / rel).read_bytes()
        if rel in _FROZEN_EOL:
            assert b"\r" not in data and b"\n" in data
            data = data.replace(b"\n", b"\r\n")
        entries.append(hashlib.sha256(data).hexdigest() + "  " + rel)
    (repo / _MANIFEST).write_text("\n".join(entries) + "\n", encoding="utf-8")


@pytest.fixture
def genuine_three_commit_lineage(tmp_path: Path) -> tuple[Path, str, str, str]:
    """Create a real 20-A -> 3-M -> 3-M git graph (no mocked Git)."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _real_git(repo, "init", "-q", "-b", "main")
    _real_git(repo, "config", "user.email", "fixture@example.invalid")
    _real_git(repo, "config", "user.name", "Fixture")
    (repo / ".gitattributes").write_text("*.csv text eol=lf\n")
    (repo / "README.md").write_text("frozen predecessor\n")
    _real_git(repo, "add", ".")
    _real_git(repo, "commit", "-qm", "frozen F4.2a")
    parent = _real_git(repo, "rev-parse", "HEAD")

    original = Path(__file__).resolve().parents[1]
    paths = (original / "docs/F4_2B_A_LOCAL_OVERLAY_FILELIST_v1.txt").read_text().splitlines()
    assert len(paths) == 20
    for rel in paths:
        p = repo / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        if rel == "docs/F4_2B_A_LOCAL_OVERLAY_FILELIST_v1.txt":
            p.write_text("\n".join(paths) + "\n")
        elif rel in _FROZEN_EOL:
            p.write_bytes(b"a,b\n1,2\n")
        else:
            p.write_text("frozen:" + rel + "\n")
    _write_overlay_manifest(repo, paths)
    _real_git(repo, "add", ".")
    _real_git(repo, "commit", "-qm", "F4.2b-A original")
    original_commit = _real_git(repo, "rev-parse", "HEAD")

    for rel in (
        "src/simfleet_edg/spatial/escort_event_index.py",
        "tests/test_f4_2b_a_event_index.py",
    ):
        (repo / rel).write_text("parser hotfix\n")
    _write_overlay_manifest(repo, paths)
    _real_git(repo, "add", ".")
    _real_git(repo, "commit", "-qm", "parser hotfix")
    parser_commit = _real_git(repo, "rev-parse", "HEAD")

    for rel in (
        "src/simfleet_edg/repro/f4_2b_a_local_sensitivity.py",
        "tests/test_f4_2b_a_runner_contract.py",
    ):
        (repo / rel).write_text("gate hotfix\n")
    _write_overlay_manifest(repo, paths)
    _real_git(repo, "add", ".")
    _real_git(repo, "commit", "-qm", "official gate hotfix")
    _real_git(repo, "update-ref", "refs/remotes/origin/main", "HEAD")
    return repo, parent, original_commit, parser_commit


def _fixture_gate(graph: tuple[Path, str, str, str]) -> dict[str, Any]:
    repo, parent, orig, parser = graph
    return _verified_git_lineage(
        repo, f4_parent=parent, original_commit=orig, parser_commit=parser
    )


def test_official_gate_accepts_real_three_commit_lineage(
    genuine_three_commit_lineage: tuple[Path, str, str, str],
) -> None:
    attestation = _fixture_gate(genuine_three_commit_lineage)
    assert attestation["overlay_hash_entries"] == 19
    assert len(attestation["diffs"]["original_20_add"]) == 20
    assert len(attestation["diffs"]["parser_3_mod"]) == 3
    assert len(attestation["diffs"]["gate_3_mod"]) == 3
    assert set(attestation["csv_eol_proofs"]) == set(_FROZEN_EOL)


def test_official_gate_rejects_wrong_ancestor(
    genuine_three_commit_lineage: tuple[Path, str, str, str],
) -> None:
    repo, _, original, parser = genuine_three_commit_lineage
    with pytest.raises(RuntimeError, match="ANCESTRY"):
        _verified_git_lineage(
            repo, f4_parent="f" * 40,
            original_commit=original, parser_commit=parser
        )


def test_official_gate_rejects_origin_divergence(
    genuine_three_commit_lineage: tuple[Path, str, str, str],
) -> None:
    repo, _, _, parser = genuine_three_commit_lineage
    _real_git(repo, "update-ref", "refs/remotes/origin/main", parser)
    with pytest.raises(RuntimeError, match="CLEAN_SYNC"):
        _fixture_gate(genuine_three_commit_lineage)


def test_official_gate_rejects_non_main(
    genuine_three_commit_lineage: tuple[Path, str, str, str],
) -> None:
    repo, _, _, _ = genuine_three_commit_lineage
    _real_git(repo, "switch", "-c", "feature")
    with pytest.raises(RuntimeError, match="BRANCH"):
        _fixture_gate(genuine_three_commit_lineage)


def test_official_gate_rejects_dirty_tree(
    genuine_three_commit_lineage: tuple[Path, str, str, str],
) -> None:
    repo, _, _, _ = genuine_three_commit_lineage
    (repo / "unexpected.txt").write_text("untracked")
    with pytest.raises(RuntimeError, match="CLEAN_SYNC"):
        _fixture_gate(genuine_three_commit_lineage)


def test_official_gate_rejects_extra_modified_file_in_commit(
    genuine_three_commit_lineage: tuple[Path, str, str, str],
) -> None:
    repo, _, _, _ = genuine_three_commit_lineage
    (repo / "README.md").write_text("unexpected change\n")
    _real_git(repo, "add", "README.md")
    _real_git(repo, "commit", "-q", "--amend", "--no-edit")
    _real_git(repo, "update-ref", "refs/remotes/origin/main", "HEAD")
    with pytest.raises(RuntimeError, match="COMMIT_SCOPE"):
        _fixture_gate(genuine_three_commit_lineage)


def test_official_gate_rejects_incomplete_overlay_manifest(
    genuine_three_commit_lineage: tuple[Path, str, str, str],
) -> None:
    repo, _, _, _ = genuine_three_commit_lineage
    p = repo / _MANIFEST
    p.write_text("\n".join(p.read_text().splitlines()[:-1]) + "\n")
    _real_git(repo, "add", _MANIFEST)
    _real_git(repo, "commit", "-q", "--amend", "--no-edit")
    _real_git(repo, "update-ref", "refs/remotes/origin/main", "HEAD")
    with pytest.raises(RuntimeError, match="MANIFEST_INCOMPLETE"):
        _fixture_gate(genuine_three_commit_lineage)


def test_frozen_csv_eol_only_two_paths_and_full_hash() -> None:
    raw = b"a,b\r\n1,2\r\n"
    wanted = hashlib.sha256(raw).hexdigest()
    for rel in _FROZEN_EOL:
        assert _verify_overlay_bytes(rel, raw, wanted) == "RAW_EXACT"
        assert _verify_overlay_bytes(
            rel, raw.replace(b"\r\n", b"\n"), wanted
        ) == "GIT_LF_CANONICAL_CRLF_EXACT"
        with pytest.raises(RuntimeError, match="HASH_MISMATCH"):
            _verify_overlay_bytes(rel, b"a,b\n1,3\n", wanted)
        with pytest.raises(RuntimeError, match="HASH_MISMATCH"):
            _verify_overlay_bytes(rel, b"a,b\r\n1,2\n", wanted)
    with pytest.raises(RuntimeError, match="HASH_MISMATCH"):
        _verify_overlay_bytes(
            "docs/F4_2B_A_LOCAL_OUTPUT_SCHEMAS_v1.csv", b"a,b\n1,2\n", wanted
        )
