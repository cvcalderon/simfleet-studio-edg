"""Static F4.2b-A exact 20-new-only precommit verifier (no Git writes)."""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path

EXPECTED = "7ec2c7aa884191ec77cf1fe6783756b78471f9c3"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify(repo: Path, *, before_install: bool = False) -> dict[str, object]:
    def git(*args: str) -> str:
        return subprocess.check_output(["git", *args], cwd=repo, text=True).strip()
    if git("branch", "--show-current") != "main" or git("rev-parse", "HEAD") != EXPECTED \
       or git("rev-parse", "refs/remotes/origin/main") != EXPECTED:
        raise RuntimeError("BLOCKED_PARENT_GIT")
    allowed_path = repo / "docs/F4_2B_A_LOCAL_OVERLAY_FILELIST_v1.txt"
    if before_install:
        raise ValueError("Use standalone entry gate before installing new overlay")
    allowed = allowed_path.read_text().splitlines()
    if len(allowed) != 20 or len(set(allowed)) != 20:
        raise RuntimeError("BLOCKED_ALLOWLIST")
    status = git("status", "--porcelain=v1", "--untracked-files=all").splitlines()
    current = {s[3:] for s in status}
    if len(current) != 20 or current != set(allowed) or any(s[:2] != "??" for s in status):
        raise RuntimeError("BLOCKED_EXACT_20_UNTRACKED_SCOPE")
    manifest = (repo / "docs/F4_2B_A_LOCAL_OVERLAY_CHECKSUMS_v1.sha256").read_text().splitlines()
    checked: set[str] = set()
    for line in manifest:
        expect, rel = line.split("  ", 1)
        if rel in checked or rel not in allowed or digest(repo / rel) != expect:
            raise RuntimeError(f"BLOCKED_OVERLAY_SHA256: {rel}")
        checked.add(rel)
    if checked != set(allowed) - {"docs/F4_2B_A_LOCAL_OVERLAY_CHECKSUMS_v1.sha256"}:
        raise RuntimeError("BLOCKED_OVERLAY_MANIFEST_COVERAGE")
    return {"status": "PREOPEN_SCOPE_PASS", "parent": EXPECTED,
            "untracked_new_paths": 20, "verified_hashes": len(checked)}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", required=True)
    args = parser.parse_args()
    print(json.dumps(verify(Path(args.repo)), sort_keys=True))


if __name__ == "__main__":
    main()
