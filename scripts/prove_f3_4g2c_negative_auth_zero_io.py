from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

from simfleet_edg.repro.f3_4g2b_joint_real_cal_auth import AuthorizationError
from simfleet_edg.repro.f3_4g2c_joint_real_cal import run_controlled_joint_real_cal


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--authorization-json", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    output = args.output_dir.expanduser().resolve()
    partial = Path(f"{output}.partial")
    shutil.rmtree(output, ignore_errors=True)
    shutil.rmtree(partial, ignore_errors=True)

    try:
        run_controlled_joint_real_cal(
            args.repo_root,
            output,
            args.config,
            args.authorization_json,
        )
    except AuthorizationError as exc:
        payload = {
            "status": "PASS",
            "negative_authorization_rejected": True,
            "cal_files_opened": [],
            "cal_rows_read": 0,
            "final_output_created": output.exists(),
            "staging_created": partial.exists(),
            "error": str(exc),
        }
        print(json.dumps(payload, indent=2, sort_keys=True))
        if output.exists() or partial.exists():
            raise SystemExit(1)
        return

    raise SystemExit("FAIL: negative authorization unexpectedly executed Joint CAL")


if __name__ == "__main__":
    main()
