from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

PHASE = "F3.4g-2b"
COMPONENT = "DGEN_JOINT_PIPELINE"
EXPECTED_FILES = {
    "person_day_context.csv",
    "participation.csv",
    "trip_count.csv",
    "chain_days.csv",
    "chain_transitions.csv",
    "time_trips.csv",
    "distance_raw.csv",
    "distance_expanded_sensitivity.csv",
}
EXPECTED_TOTAL_ROWS = 6341


class AuthorizationError(RuntimeError):
    """Raised before any Joint real-CAL content I/O is permitted."""


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


def load_joint_real_cal_authorization(
    authorization_path: Path,
    repo_root: Path,
) -> dict[str, Any]:
    """Validate positive authorization before CAL content I/O or staging."""
    if not authorization_path.is_file():
        raise AuthorizationError("Authorization file missing")

    payload = json.loads(authorization_path.read_text(encoding="utf-8"))
    state = repository_state(repo_root)

    checks = {
        "phase": payload.get("phase") == PHASE,
        "component": payload.get("component") == COMPONENT,
        "branch_main": state["branch"] == "main",
        "head_origin_equal": state["head"] == state["origin_main"],
        "worktree_clean": state["porcelain"] == "",
        "commit_exact": payload.get("authorized_implementation_commit") == state["head"],
        "real_cal_open": payload.get("joint_real_cal_open_authorized") is True,
        "joint_gate_authorized": (
            payload.get("joint_gate_evaluation_authorized") is True
        ),
        "allowed_files_exact": set(payload.get("allowed_cal_files", []))
        == EXPECTED_FILES,
        "row_count_exact": (
            payload.get("expected_total_physical_rows") == EXPECTED_TOTAL_ROWS
        ),
        "selected_count": payload.get("selected_pipeline_artifacts") == 5,
        "reference_count": payload.get("reference_pipeline_artifacts") == 5,
        "selection_none": payload.get("candidate_selection_at_entry") == "NONE",
        "test_closed": payload.get("test_open_authorized") is False,
        "g2_not_evaluated": payload.get("formal_g2") == "NOT_EVALUATED",
    }

    failed = [name for name, passed in checks.items() if not passed]
    if failed:
        raise AuthorizationError(f"Authorization rejected: {failed}")

    return {
        **payload,
        "status": "PASS",
        "repository_head": state["head"],
        "cal_io_authorized": True,
        "staging_creation_authorized": True,
    }
