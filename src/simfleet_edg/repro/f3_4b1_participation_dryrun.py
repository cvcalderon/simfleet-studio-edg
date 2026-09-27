"""CLI for F3.4b-1 synthetic Participation CAL runner dry-run."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from simfleet_edg.evaluation.participation_cal_dryrun import (
    load_dryrun_config,
    run_synthetic_participation_dryrun,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--skip-artifact-smoke", action="store_true")
    args = parser.parse_args()
    config = load_dryrun_config(args.config)
    repo_root = Path.cwd()
    manifest = run_synthetic_participation_dryrun(
        repo_root,
        args.output_dir,
        validate_frozen_artifacts=not args.skip_artifact_smoke,
    )
    result = {
        **manifest,
        "config_phase": config["phase"],
        "cal_read_performed": False,
    }
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
