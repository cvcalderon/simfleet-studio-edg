from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path

from simfleet_edg.repro.f3_4g2b_joint_real_cal_auth import (
    AuthorizationError,
    load_joint_real_cal_authorization,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--template", type=Path, required=True)
    args = parser.parse_args()

    with tempfile.TemporaryDirectory() as temporary:
        staging = Path(temporary) / "should_not_exist.partial"
        cal_opened: list[str] = []

        try:
            load_joint_real_cal_authorization(args.template, args.repo_root)
        except AuthorizationError as exc:
            payload = {
                "status": "PASS",
                "negative_authorization_rejected": True,
                "cal_files_opened": cal_opened,
                "cal_rows_read": 0,
                "staging_created": staging.exists(),
                "error": str(exc),
            }
            print(json.dumps(payload, indent=2, sort_keys=True))
            if staging.exists() or cal_opened:
                raise SystemExit(1)
            return

        raise SystemExit("FAIL: tracked negative authorization template was accepted")


if __name__ == "__main__":
    main()
