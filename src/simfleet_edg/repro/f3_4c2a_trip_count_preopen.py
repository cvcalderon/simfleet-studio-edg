from __future__ import annotations

import argparse
import json
from pathlib import Path

from simfleet_edg.evaluation.trip_count_cal_preopen import (
    load_preopen_config,
    run_synthetic_trip_count_preopen,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--skip-artifact-smoke", action="store_true")
    args = parser.parse_args()

    config = load_preopen_config(args.config)
    manifest = run_synthetic_trip_count_preopen(
        Path.cwd(),
        args.output_dir,
        validate_artifacts=not args.skip_artifact_smoke,
    )
    print(
        json.dumps(
            {
                **manifest,
                "config_phase": config["phase"],
                "cal_read_performed": False,
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
