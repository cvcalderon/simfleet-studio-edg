from __future__ import annotations

import argparse
import json
import shutil
import tempfile
from pathlib import Path

from simfleet_edg.repro.f1_pconstr_cal01_runner import AuthorizationError, run_controlled_cal


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", required=True, type=Path)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--authorization-template", required=True, type=Path)
    args = parser.parse_args()
    out = Path("/tmp/f1_pconstr_cal01_negative_should_not_exist")
    partial = Path(f"{out}.partial")
    shutil.rmtree(out, ignore_errors=True)
    shutil.rmtree(partial, ignore_errors=True)
    with tempfile.TemporaryDirectory() as temporary:
        external_template = Path(temporary) / "negative_execution_authorization.json"
        external_template.write_bytes(args.authorization_template.read_bytes())
        try:
            run_controlled_cal(
                args.repo_root,
                args.config,
                external_template,
                Path("/definitely/not/opened/impl03.zip"),
                out,
            )
        except AuthorizationError as exc:
            payload = {
                "status": "PASS",
                "negative_authorization_rejected": True,
                "negative_template_externalized": True,
                "cal_rows_materialized": 0,
                "candidate_bundle_opened": False,
                "staging_created": partial.exists(),
                "final_output_created": out.exists(),
                "error": str(exc),
            }
            print(json.dumps(payload, indent=2, sort_keys=True))
            if out.exists() or partial.exists():
                raise SystemExit(1)
            return
    raise SystemExit("FAIL: negative execution authorization unexpectedly accepted")


if __name__ == "__main__":
    main()
