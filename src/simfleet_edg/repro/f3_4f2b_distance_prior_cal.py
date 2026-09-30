from __future__ import annotations

import argparse
import json
from pathlib import Path

from simfleet_edg.evaluation.distance_prior_cal_real import run_controlled_distance_prior_cal


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--authorization-json", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--no-stochastic-evidence", action="store_true")
    args = parser.parse_args()
    manifest = run_controlled_distance_prior_cal(Path.cwd(), args.output_dir, args.config, args.authorization_json, write_stochastic_evidence=not args.no_stochastic_evidence)
    print(json.dumps(manifest, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
