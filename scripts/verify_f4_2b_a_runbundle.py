"""Verify postpush A/B exact bytes and all 11 pre-registered variants."""
from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
from pathlib import Path
from typing import Any


def files(root: Path) -> dict[str, str]:
    return {x.name: hashlib.sha256(x.read_bytes()).hexdigest()
            for x in root.iterdir() if x.is_file()}


def verify(root: Path) -> dict[str, Any]:
    manifest = json.loads((root / "runbundle_manifest_v1.json").read_text())
    a = files(root / "A")
    b = files(root / "B")
    if a != b or a != manifest["sha256_by_relative_path"] or len(a) != 25:
        raise RuntimeError("BLOCKED_REPRO_SHA256")
    if manifest["status"] != "RETURN_TO_MAIN_NO_G3" or not manifest["pair_exact"]:
        raise RuntimeError("Wrong MAIN return status")
    for prefix in ("B0_NO_LINK", *(f"B2_SRV{year}_HH{i:03d}"
                                for year in (2018, 2023) for i in (0, 25, 50, 75, 100))):
        filename = f"escort_location_proposals_{prefix}_v1.csv.gz"
        auditname = f"escort_audit_{prefix}_v1.json"
        if filename not in a or auditname not in a:
            raise RuntimeError("Missing pre-registered variant")
        with gzip.open(root / "A" / filename, "rt", encoding="utf-8", newline="") as f:
            count = sum(1 for _ in csv.DictReader(f))
        with (root / "A" / auditname).open(encoding="utf-8") as f:
            audit = json.load(f)
        if count != 18871 or audit["total_escort_events"] != 18871 or sum(audit["statuses"].values()) != 18871:
            raise RuntimeError("Not all 18871 events preserved")
    return {"status": "RUNBUNDLE_VERIFIER_PASS", "identical_A_B_files": len(a),
            "variant_count": 11, "event_rows_per_variant": 18871}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runbundle", required=True)
    args = parser.parse_args()
    print(json.dumps(verify(Path(args.runbundle)), sort_keys=True))


if __name__ == "__main__":
    main()
