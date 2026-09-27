"""Safe F3.3d entry point.

This entry point does not read CAL. The decisive repository audit is the verifier script.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import yaml


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    args = parser.parse_args()

    cfg = yaml.safe_load(Path(args.config).read_text(encoding="utf-8"))
    before = cfg["boundaries_before_gate"]
    if before != {
        "cal_partition": "UNOPENED",
        "cal_rows_read": 0,
        "test_partition": "SEALED",
        "test_rows_read": 0,
        "candidate_selection": "NONE",
    }:
        raise SystemExit("PRE-CAL boundary is not pristine")

    result = {
        "status": "PASS",
        "phase": "F3.3d",
        "gate_evaluation": "READY_FOR_REPOSITORY_VERIFIER",
        "cal_partition_before_gate": "UNOPENED",
        "cal_rows_read": 0,
        "test_partition": "SEALED",
        "test_rows_read": 0,
        "candidate_selection": "NONE",
        "test_open_authorized": False,
    }
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
