from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

from simfleet_edg.repro.f3_4g2e_test_auth import (
    TestAuthorizationError as HeldoutAuthorizationError,
)
from simfleet_edg.repro.f3_4g2f_heldout_test_runner import (
    run_controlled_heldout_test,
)


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
        run_controlled_heldout_test(
            args.repo_root,
            output,
            args.config,
            args.authorization_json,
        )
    except HeldoutAuthorizationError as exc:
        payload = {
            "status": "PASS",
            "negative_test_authorization_rejected": True,
            "test_outcome_source_files_opened": [],
            "test_outcome_rows_read": 0,
            "test_materialized": False,
            "staging_created": partial.exists(),
            "holdout_consumed": False,
            "formal_g2": "NOT_EVALUATED",
            "error": str(exc),
        }
        print(json.dumps(payload, indent=2, sort_keys=True))
        if output.exists() or partial.exists():
            raise SystemExit(1)
        return

    raise SystemExit("FAIL: negative TEST authorization was accepted")


if __name__ == "__main__":
    main()
