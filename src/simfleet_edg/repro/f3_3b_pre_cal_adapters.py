"""Safe PRE-CAL entry point: validate and smoke-test adapters without reading CAL."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import yaml

from simfleet_edg.evaluation.cal_adapter_common import load_registry, sha256_file
from simfleet_edg.evaluation.cal_adapter_factory import build_adapter, synthetic_smoke


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    args = parser.parse_args()

    repo_root = Path.cwd()
    cfg_path = repo_root / args.config
    cfg = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))

    if cfg["cal_partition"] != "UNOPENED" or cfg["test_partition"] != "SEALED":
        raise RuntimeError("F3.3b safe entry point requires CAL unopened and TEST sealed")

    registry_path = repo_root / cfg["candidate_registry"]["path"]
    if sha256_file(registry_path) != cfg["candidate_registry"]["sha256"]:
        raise RuntimeError("Candidate registry SHA mismatch")
    records = load_registry(registry_path)

    results = []
    for i, record in enumerate(records):
        adapter = build_adapter(repo_root, record)
        smoke = synthetic_smoke(adapter, seed=202609260000 + i)
        results.append({"artifact_id": record.artifact_id, "output_keys": sorted(smoke)})

    print(json.dumps({
        "status": "PASS",
        "phase": "F3.3b",
        "cal_partition": "UNOPENED",
        "test_partition": "SEALED",
        "candidate_selection": "NONE",
        "artifact_adapters": len(records),
        "synthetic_cases": len(results),
        "cal_rows_read": 0,
        "test_rows_read": 0,
    }, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
