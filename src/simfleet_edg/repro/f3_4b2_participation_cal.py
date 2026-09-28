from __future__ import annotations

import argparse
import json
from pathlib import Path

from simfleet_edg.evaluation.participation_cal_real import (
    run_controlled_participation_cal,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="F3.4b-2 controlled real CAL: DG_PARTICIPATION"
    )
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--authorization-json", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    manifest = run_controlled_participation_cal(
        Path.cwd(), args.output_dir, args.config, args.authorization_json
    )
    print(json.dumps(manifest, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
