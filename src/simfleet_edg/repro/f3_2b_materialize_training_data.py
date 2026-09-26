"""F3.2b official materialization of frozen D_GEN TRAIN/CAL tables."""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path
from typing import Any

import yaml

from simfleet_edg.demand.training_data import materialize_training_data


def _project_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _git(root: Path, *args: str) -> str:
    result = subprocess.run(["git", *args], cwd=root, check=True, capture_output=True, text=True)
    return result.stdout.strip()


def _git_state(root: Path) -> dict[str, Any]:
    commit = _git(root, "rev-parse", "HEAD")
    branch = _git(root, "branch", "--show-current")
    clean = not bool(_git(root, "status", "--porcelain"))
    upstream = None
    ahead = behind = None
    try:
        upstream = _git(root, "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}")
        counts = _git(root, "rev-list", "--left-right", "--count", "HEAD...@{u}").split()
        ahead, behind = map(int, counts)
    except (subprocess.CalledProcessError, ValueError):
        pass
    return {
        "commit": commit,
        "branch": branch,
        "worktree_clean": clean,
        "upstream": upstream,
        "ahead": ahead,
        "behind": behind,
    }


def _require_official_git(root: Path, config: dict[str, Any]) -> dict[str, Any]:
    state = _git_state(root)
    parent = str(config["required_design_parent_commit"])
    ancestor = subprocess.run(
        ["git", "merge-base", "--is-ancestor", parent, state["commit"]],
        cwd=root,
        check=False,
        capture_output=True,
    ).returncode == 0
    required = {
        "branch_main": state["branch"] == str(config["branch"]),
        "worktree_clean": bool(state["worktree_clean"]),
        "upstream": state["upstream"] == str(config["upstream"]),
        "ahead_zero": state["ahead"] == 0,
        "behind_zero": state["behind"] == 0,
        "design_parent_is_ancestor": ancestor,
    }
    failed = [name for name, ok in required.items() if not ok]
    if failed:
        raise RuntimeError(f"Official F3.2b git gate failed: {failed}; state={state}")
    return state


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()

    root = _project_root()
    config_path = args.config if args.config.is_absolute() else root / args.config
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    git_state = _require_official_git(root, config)
    contract = config["contract"]
    out = args.out or Path(str(config["output_root"]))
    out = out if out.is_absolute() else root / out

    materialize_training_data(
        root=root,
        out=out,
        source_manifest_path=root / str(contract["source_manifest"]),
        expected_counts_path=root / str(contract["expected_counts"]),
        schema_path=root / str(contract["dataset_schema"]),
        activity_recoding_path=root / "configs/reproduction/reference/f0_2d_activity_recoding_v1.csv",
    )
    manifest_path = out / "materialization_manifest.json"
    full_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    full_manifest["git"] = git_state
    full_manifest["config"] = str(config_path.relative_to(root))
    full_manifest["design_parent_commit"] = str(config["required_design_parent_commit"])
    manifest_path.write_text(
        json.dumps(full_manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    # checksums include the final git-enriched manifest.
    from simfleet_edg.demand.training_data import _all_checksums  # noqa: PLC0415

    (out / "checksums.sha256").write_text(
        "\n".join(_all_checksums(out)) + "\n", encoding="utf-8"
    )
    print(json.dumps({"status": "PASS", "output": str(out.relative_to(root))}, indent=2))


if __name__ == "__main__":
    main()
