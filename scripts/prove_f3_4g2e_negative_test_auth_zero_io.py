from __future__ import annotations

import argparse
import json
from pathlib import Path

from simfleet_edg.repro.f3_4g2e_test_auth import (
    TestAuthorizationError,
    load_heldout_test_authorization,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--template", type=Path, required=True)
    args = parser.parse_args()

    test_files_opened: list[str] = []
    test_rows_read = 0
    staging_created = False

    try:
        load_heldout_test_authorization(args.template, args.repo_root)
    except TestAuthorizationError as exc:
        payload = {
            "status": "PASS",
            "negative_test_authorization_rejected": True,
            "test_outcome_files_opened": test_files_opened,
            "test_outcome_rows_read": test_rows_read,
            "staging_created": staging_created,
            "holdout_consumed": False,
            "formal_g2": "NOT_EVALUATED",
            "error": str(exc),
        }
        print(json.dumps(payload, indent=2, sort_keys=True))
        return

    raise SystemExit("FAIL: negative tracked TEST authorization was accepted")


if __name__ == "__main__":
    main()
