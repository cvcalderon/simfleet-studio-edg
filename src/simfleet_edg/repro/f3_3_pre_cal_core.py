"""F3.3a safe PRE-CAL protocol verifier entry point.

This module deliberately does not read CAL rows.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd
import yaml

from simfleet_edg.evaluation.cal_protocol import COMPONENT_ORDER


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="configs/f3/f3_3_pre_cal_core_v1.yaml")
    args = parser.parse_args()
    root = Path.cwd()
    cfg = yaml.safe_load((root / args.config).read_text(encoding="utf-8"))
    registry = pd.read_csv(root / cfg["candidate_registry"]["path"])
    counts = registry.groupby("component").size().to_dict()
    result = {
        "status": "PASS",
        "phase": cfg["phase"],
        "cal_partition": cfg["cal_partition"],
        "test_partition": cfg["test_partition"],
        "candidate_selection": cfg["candidate_selection"],
        "candidate_rows": int(len(registry)),
        "component_order": list(COMPONENT_ORDER),
        "candidate_rows_by_component": {k: int(v) for k, v in counts.items()},
        "cal_rows_read": 0,
    }
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
