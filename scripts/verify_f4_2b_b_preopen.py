"""F4.2b-B static PRE-COMMIT exact-scope and frozen-byte verifier.

Read-only. Does not run Git mutations or scientific experiments.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any

import yaml  # type: ignore[import-untyped]

EXPECTED = "1fdfd815fb5085cbc674b66baecd932a9bcabff9"
ALLOWLIST = "docs/F4_2B_B_OVERLAY_FILELIST_v1.txt"
CHECKSUMS = "docs/F4_2B_B_OVERLAY_CHECKSUMS_v1.sha256"
FROZEN = (("docs/F4_2A_OVERLAY_FILELIST_v1.txt",
           "docs/F4_2A_OVERLAY_CHECKSUMS_v1.sha256", 26, 25),
          ("docs/F4_2B_A_LOCAL_OVERLAY_FILELIST_v1.txt",
           "docs/F4_2B_A_LOCAL_OVERLAY_CHECKSUMS_v1.sha256", 20, 19))
# Six, and ONLY six, MAIN-proven Git LF -> original CRLF canonicalizations.
CRLF = frozenset({
    "docs/F4_2A_ACTIVITY_RESOLUTION_MATRIX_v1.csv",
    "docs/F4_2A_CANDIDATE_MATRIX_v1.csv",
    "docs/F4_2A_METRIC_REGISTRY_v1.csv",
    "docs/F4_2A_OUTPUT_SCHEMAS_v1.csv",
    "docs/F4_2B_A_LOCAL_VALIDATION_GATES_v1.csv",
    "docs/F4_2B_A_LOCAL_VARIANT_MATRIX_v1.csv",
})


def _git(root: Path, *args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=root, text=True).strip()


def sha(blob: bytes) -> str:
    return hashlib.sha256(blob).hexdigest()


def manifest(root: Path, rel: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for line in (root / rel).read_text().splitlines():
        checksum, path = line.split("  ", 1)
        if (path in result or len(checksum) != 64 or path.startswith("/")
                or ".." in Path(path).parts):
            raise RuntimeError("BLOCKED_CHECKSUM_MANIFEST_INVALID")
        result[path] = checksum
    return result


def verify_prior_overlays(repo: Path) -> dict[str, Any]:
    results: dict[str, int] = {}
    # A six-member *closed* exception list, with independent cryptographic
    # proof for every path. On a real checkout a CSV may already retain its
    # original CRLF bytes (exact expected SHA); this is stronger evidence than
    # the Git-normalized LF -> original CRLF reconstruction.
    six_proofs: dict[str, str] = {}
    for paths_rel, checksums_rel, length, entries in FROZEN:
        paths = (repo / paths_rel).read_text().splitlines()
        checksums = manifest(repo, checksums_rel)
        if (len(paths) != length or len(set(paths)) != length
                or checksums.keys() != set(paths) - {checksums_rel}
                or len(checksums) != entries):
            raise RuntimeError("BLOCKED_PREVIOUS_OVERLAY_SCOPE")
        for path, expected in checksums.items():
            data = (repo / path).read_bytes()
            if sha(data) == expected:
                if path in CRLF:
                    six_proofs[path] = "ORIGINAL_FROZEN_SHA_BYTE_EXACT"
                continue
            # The ONLY permitted non-exact case is a declared CSV in the
            # six-member MAIN reconciliation list with LF-only checkout bytes
            # that reconstruct the precise frozen SHA (not arbitrary EOL
            # normalization or an unchecked exception).
            if (path not in CRLF or b"\r" in data or b"\n" not in data
                    or sha(data.replace(b"\n", b"\r\n")) != expected):
                raise RuntimeError("BLOCKED_PREVIOUS_FROZEN_HASH: " + path)
            six_proofs[path] = "GIT_LF_TO_ORIGINAL_CRLF_SHA_PROVEN"
        results[checksums_rel] = entries
    if set(six_proofs) != CRLF:
        raise RuntimeError("BLOCKED_PREVIOUS_CSV_CANONICALIZATION_PROOF")
    return {"prior_entries": results,
            "six_explicit_csv_sha_proofs": dict(sorted(six_proofs.items())),
            "six_explicit_csv_sha_reconstructions": sorted(
                path for path, proof in six_proofs.items()
                if proof == "GIT_LF_TO_ORIGINAL_CRLF_SHA_PROVEN")}


def verify_protected(repo: Path) -> int:
    cfg = yaml.safe_load((repo / "configs/f4/f4_2b_b_partial_integration_preopen_v1.yaml").read_text())
    expected = cfg["baseline_protected_sha256"]
    if len(expected) != 19:
        raise RuntimeError("BLOCKED_KEY_PROTECTED_COUNT")
    for rel, checksum in expected.items():
        if sha((repo / rel).read_bytes()) != checksum:
            raise RuntimeError("BLOCKED_KEY_PROTECTED_SHA: " + rel)
    return len(expected)


def verify(repo: Path) -> dict[str, Any]:
    if (_git(repo, "symbolic-ref", "--quiet", "--short", "HEAD") != "main"
            or _git(repo, "rev-parse", "HEAD") != EXPECTED
            or _git(repo, "rev-parse", "refs/remotes/origin/main") != EXPECTED):
        raise RuntimeError("BLOCKED_PRECOMMIT_GIT_HEAD")
    paths = (repo / ALLOWLIST).read_text().splitlines()
    if len(paths) != 25 or len(set(paths)) != 25 or CHECKSUMS not in paths:
        raise RuntimeError("BLOCKED_EXACT_25_ALLOWLIST")
    statuses = _git(repo, "status", "--porcelain=v1", "--untracked-files=all").splitlines()
    if (len(statuses) != 25 or any(line[:2] != "??" for line in statuses)
            or {line[3:] for line in statuses} != set(paths)):
        raise RuntimeError("BLOCKED_EXACT_25_NEW_PATHS_ONLY")
    sums = manifest(repo, CHECKSUMS)
    if sums.keys() != set(paths) - {CHECKSUMS}:
        raise RuntimeError("BLOCKED_F4_2B_B_MANIFEST_FILE_SET")
    for rel, expected in sums.items():
        if sha((repo / rel).read_bytes()) != expected:
            raise RuntimeError("BLOCKED_F4_2B_B_NEW_FILE_HASH: " + rel)
    previous = verify_prior_overlays(repo)
    protected = verify_protected(repo)
    return {"status": "F4_2B_B_PRECOMMIT_EXACT_SCOPE_PASS", "parent": EXPECTED,
            "untracked_only": 25, "new_hashes_verified": len(sums), "key_protected_sha_pass": protected,
            **previous, "stop": "USER_MANUAL_PYCHARM_COMMIT_PUSH"}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(verify(args.repo), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
