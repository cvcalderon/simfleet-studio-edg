"""Safe F3.3c PRE-CAL execution-harness entry point."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import yaml

from simfleet_edg.evaluation.cal_access_guard import PartitionAccess


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    args = parser.parse_args()

    config = yaml.safe_load(Path(args.config).read_text(encoding="utf-8"))
    PartitionAccess(
        cal_authorized=bool(config["boundaries"]["cal_open_authorized"]),
        test_authorized=bool(config["boundaries"]["test_open_authorized"]),
    ).assert_pre_cal()

    result = {
        "status": "PASS",
        "phase": "F3.3c",
        "parent_commit": config["identity"]["parent_commit"],
        "stochastic_replicates": config["protocol"]["stochastic_replicates"],
        "household_bootstrap_replicates": config["protocol"]["household_bootstrap_replicates"],
        "evidence_schema": config["protocol"]["evidence_schema"],
        "cal_partition": "UNOPENED",
        "cal_rows_read": 0,
        "test_partition": "SEALED",
        "test_rows_read": 0,
        "candidate_selection": "NONE",
    }
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
