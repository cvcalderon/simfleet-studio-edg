"""Static F4.2a PRE-COMMIT verifier; never commits or performs science."""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path

PARENT = "61f29671a1e2a562d000bd6a1be45366a6630568"
DESIGN_SHA = "9d5189aead090e1acfb5eb1a58cedaf57e10d9b8fd7a7c6e516147022a1ee382"
MAIN_SHA = "78ccb295c2388cf051e0af5f01daa0fbd6f3a782468f75171f51f302a1ad290b"
RUFF_BASELINE_SHA = "17091717a5f573780b2b7e158f644d1d7fac764e38a62a3bfbb3377926dac2a9"
MYPY_BASELINE_SHA = "55b83b6d30605b60d6a515f9fa64dd927491c0eab93995239a5d4ae31b5da964"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git(repo: Path, *args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=repo, text=True).strip()


def verify(repo: Path, baseline: Path | None = None) -> dict[str, object]:
    expected = set((repo / "docs/F4_2A_OVERLAY_FILELIST_v1.txt").read_text(encoding="utf-8").splitlines())
    if len(expected) != 26:
        raise RuntimeError("Overlay exact 26-path scope is not met")
    if git(repo, "branch", "--show-current") != "main":
        raise RuntimeError("Expected main branch")
    if git(repo, "rev-parse", "HEAD") != PARENT or git(repo, "rev-parse", "origin/main") != PARENT:
        raise RuntimeError("Precommit parent HEAD/origin mismatch")
    changed = git(repo, "status", "--porcelain=v1", "--untracked-files=all").splitlines()
    actual = {line[3:] for line in changed}
    if actual != expected or any(not line.startswith("?? ") for line in changed):
        raise RuntimeError(f"Exact new-only scope mismatch: {[x for x in changed if x[3:] not in expected][:10]}")
    for check, expected_sha in (("F4_2A_CORE_SPATIAL_CANDIDATE_DESIGN_FREEZE_v1.md", DESIGN_SHA),
                                ("F4_2A_MAIN_SCIENTIFIC_PREOPEN_SPEC_v1.yaml", MAIN_SHA)):
        if sha(repo / "docs" / check) != expected_sha:
            raise RuntimeError(f"Normative authority content not frozen: {check}")
    manifest = repo / "docs/F4_2A_OVERLAY_CHECKSUMS_v1.sha256"
    checks = manifest.read_text().splitlines()
    if len(checks) != 25:
        raise RuntimeError("Checksum manifest must cover exactly 25 non-self paths")
    hashed: set[str] = set()
    for entry in checks:
        digest, path = entry.split("  ", 1)
        if path not in expected or path == "docs/F4_2A_OVERLAY_CHECKSUMS_v1.sha256":
            raise RuntimeError("Manifest covers out-of-scope or self path")
        if sha(repo / path) != digest:
            raise RuntimeError(f"F4.2a overlay hash mismatch: {path}")
        hashed.add(path)
    if hashed != expected - {"docs/F4_2A_OVERLAY_CHECKSUMS_v1.sha256"}:
        raise RuntimeError("Manifest missing overlay path")
    if baseline:
        parent = json.loads((baseline / "BASELINE_RESULT.json").read_text())
        if (parent["status"] != "PASS" or not parent["post_check_repo_unchanged"]
                or parent["parent_head"] != PARENT
                or parent["quality"]["ruff"]["normalized_sha256"] != RUFF_BASELINE_SHA
                or parent["quality"]["mypy"]["normalized_sha256"] != MYPY_BASELINE_SHA):
            raise RuntimeError("Frozen parent quality fingerprint mismatch")
    return {"status": "PASS", "phase": "F4_2A_PRECOMMIT", "git_parent": PARENT,
            "changed_paths": len(actual), "overlay_checksum_paths": len(hashed),
            "action": "STOP_PRE_COMMIT", "manual_pyCharm_commit_push_required": True,
            "g3_opened": False}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--baseline-evidence-dir", type=Path)
    args = parser.parse_args()
    print(json.dumps(verify(args.repo_root, args.baseline_evidence_dir), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
