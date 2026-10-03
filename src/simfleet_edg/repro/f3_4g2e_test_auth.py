from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

PHASE = "F3.4g-2e"
COMPONENT = "DGEN_JOINT_PIPELINE"
EXPECTED_INPUTS = {
    "person_day_context.csv",
    "participation.csv",
    "trip_count.csv",
    "chain_days.csv",
    "chain_transitions.csv",
    "time_trips.csv",
    "distance_raw.csv",
    "distance_expanded_sensitivity.csv",
}


class TestAuthorizationError(RuntimeError):
    """Raised before any held-out TEST content I/O is permitted."""


def _git(repo_root: Path, *args: str) -> str:
    return subprocess.check_output(
        ["git", *args],
        cwd=repo_root,
        text=True,
    ).strip()


def repository_state(repo_root: Path) -> dict[str, Any]:
    return {
        "branch": _git(repo_root, "branch", "--show-current"),
        "head": _git(repo_root, "rev-parse", "HEAD"),
        "origin_main": _git(repo_root, "rev-parse", "origin/main"),
        "porcelain": _git(repo_root, "status", "--porcelain"),
    }


def load_heldout_test_authorization(
    authorization_path: Path,
    repo_root: Path,
) -> dict[str, Any]:
    if not authorization_path.is_file():
        raise TestAuthorizationError("TEST authorization file missing")

    payload = json.loads(authorization_path.read_text(encoding="utf-8"))
    state = repository_state(repo_root)

    checks = {
        "phase": payload.get("phase") == PHASE,
        "component": payload.get("component") == COMPONENT,
        "branch_main": state["branch"] == "main",
        "head_origin_equal": state["head"] == state["origin_main"],
        "worktree_clean": state["porcelain"] == "",
        "commit_exact": payload.get("authorized_implementation_commit") == state["head"],
        "test_open": payload.get("heldout_test_open_authorized") is True,
        "g2_authorized": payload.get("formal_g2_evaluation_authorized") is True,
        "inputs_exact": set(payload.get("logical_test_inputs", [])) == EXPECTED_INPUTS,
        "replicates_32": payload.get("stochastic_replicates") == 32,
        "seed_exact": payload.get("master_seed") == 20261003,
        "selection_none": payload.get("candidate_selection") == "NONE",
        "post_test_tuning_forbidden": (
            payload.get("post_test_tuning_authorized") is False
        ),
        "same_holdout_rerun_forbidden": (
            payload.get("same_holdout_rerun_after_content_io") is False
        ),
    }

    failed = [name for name, passed in checks.items() if not passed]
    if failed:
        raise TestAuthorizationError(f"TEST authorization rejected: {failed}")

    return {
        **payload,
        "status": "PASS",
        "repository_head": state["head"],
        "test_content_io_authorized": True,
        "staging_creation_authorized": True,
    }
