"""F4.2b-B exact new-path authority and frozen hash declarations."""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]


def test_scope_exact_25_and_protected_19() -> None:
    scope = (ROOT / "docs/F4_2B_B_OVERLAY_FILELIST_v1.txt").read_text().splitlines()
    cfg = yaml.safe_load((ROOT / "configs/f4/f4_2b_b_partial_integration_preopen_v1.yaml").read_text())
    assert len(scope) == len(set(scope)) == 25
    assert all((ROOT / p).is_file() for p in scope)
    assert len(cfg["baseline_protected_sha256"]) == 19
    assert not set(scope).intersection(cfg["baseline_protected_sha256"])
    assert cfg["expected_real_clone"]["head"] == (
        "1fdfd815fb5085cbc674b66baecd932a9bcabff9")


def test_six_and_only_six_original_eol_exceptions() -> None:
    spec = importlib.util.spec_from_file_location(
        "f4_b2b_preopen", ROOT / "scripts/verify_f4_2b_b_preopen.py")
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert len(mod.CRLF) == 6
    assert all(rel.endswith(".csv") for rel in mod.CRLF)


def _previous_overlay_snapshot(tmp_path: Path, mod: object) -> None:
    """Make a local copy of the two already-committed overlay manifests and files."""
    for list_rel, checksums_rel, _, _ in mod.FROZEN:
        path_list = (ROOT / list_rel).read_text().splitlines()
        paths = [list_rel, checksums_rel, *path_list]
        for rel in set(paths):
            dest = tmp_path / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes((ROOT / rel).read_bytes())


def test_each_of_six_has_original_sha_proof_in_mixed_checkout(tmp_path: Path) -> None:
    """An original-CRLF checkout is valid; some entries may remain Git-LF."""
    spec = importlib.util.spec_from_file_location(
        "f4_b2b_preopen", ROOT / "scripts/verify_f4_2b_b_preopen.py")
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    _previous_overlay_snapshot(tmp_path, mod)

    # For up to three pre-normalized LF files, reconstruct the actual
    # original CRLF bytes and ensure their frozen hash matches first.
    for rel in sorted(mod.CRLF)[:3]:
        target = tmp_path / rel
        data = target.read_bytes()
        expected = next(
            mod.manifest(tmp_path, checksum_rel)[rel]
            for _, checksum_rel, _, _ in mod.FROZEN
            if rel in mod.manifest(tmp_path, checksum_rel)
        )
        if mod.sha(data) != expected:
            assert b"\r" not in data and b"\n" in data
            reconstructed = data.replace(b"\n", b"\r\n")
            assert mod.sha(reconstructed) == expected
            target.write_bytes(reconstructed)

    result = mod.verify_prior_overlays(tmp_path)
    assert set(result["six_explicit_csv_sha_proofs"]) == mod.CRLF
    assert len(result["six_explicit_csv_sha_proofs"]) == 6
    assert set(result["six_explicit_csv_sha_proofs"].values()) <= {
        "ORIGINAL_FROZEN_SHA_BYTE_EXACT",
        "GIT_LF_TO_ORIGINAL_CRLF_SHA_PROVEN",
    }


def test_any_unproven_member_remains_blocked(tmp_path: Path) -> None:
    spec = importlib.util.spec_from_file_location(
        "f4_b2b_preopen", ROOT / "scripts/verify_f4_2b_b_preopen.py")
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    _previous_overlay_snapshot(tmp_path, mod)
    bad = tmp_path / sorted(mod.CRLF)[0]
    bad.write_bytes(bad.read_bytes() + b"UNAUTHORIZED")
    with pytest.raises(RuntimeError, match="BLOCKED_PREVIOUS_FROZEN_HASH"):
        mod.verify_prior_overlays(tmp_path)
