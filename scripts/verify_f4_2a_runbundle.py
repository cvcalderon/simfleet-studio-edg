"""Verify frozen F4.2a post-push RunBundle; never initiate G3."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(2**20), b""):
            h.update(block)
    return h.hexdigest()


def verify_runbundle(root: Path) -> dict[str, Any]:
    manifest = json.loads((root / "run_manifest.json").read_text(encoding="utf-8"))
    hashes = json.loads((root / "runbundle_sha256.json").read_text(encoding="utf-8"))
    if not hashes or any(sha(root / file) != expected for file, expected in hashes.items()):
        raise ValueError("RunBundle file SHA-256 mismatch")
    if (manifest["status"] != "RETURN_TO_MAIN" or not manifest["full_dgen_A_B_exact"]
            or not manifest["spatial_two_run_exact"] or manifest["g3_opened"]
            or manifest["cal_reads"] or manifest["mid_test_reads"]
            or manifest["scenario"]["persons"] != 100000):
        raise ValueError("Frozen scientific boundary or full 100k gate failed")
    a = {name.removeprefix("spatial_1/"): digest for name, digest in hashes.items()
         if name.startswith("spatial_1/") }
    b = {name.removeprefix("spatial_2/"): digest for name, digest in hashes.items()
         if name.startswith("spatial_2/") }
    if a != b:
        raise ValueError("Spatial paired replay file hashes differ")
    return {"status": "PASS", "files_verified": len(hashes), "spatial_files": len(a),
            "candidate_promotable_internal_only": manifest["candidate_promotable_internal_only"],
            "return_to_main": True, "g3_opened": False}


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--runbundle", type=Path, required=True)
    args = p.parse_args()
    print(json.dumps(verify_runbundle(args.runbundle), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
