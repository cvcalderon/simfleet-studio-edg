"""R0: capture and validate the execution environment before PRE-F3 reproduction."""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path
from typing import Any

import yaml

from simfleet_edg.common.environment import (
    Timer,
    collect_environment,
    installed_distribution_version,
    pip_freeze,
    python_distributions,
    sha256_file,
    write_csv,
    write_json,
)


def _load_config(path: Path) -> dict[str, Any]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("R0 config must be a YAML mapping")
    return payload


def _project_root_from_config(config_path: Path) -> Path:
    # configs/reproduction/r0_environment.yaml -> repository root
    return config_path.resolve().parents[2]


def _check(name: str, observed: Any, expected: Any, passed: bool) -> dict[str, str]:
    return {
        "check": name,
        "status": "PASS" if passed else "FAIL",
        "observed": json.dumps(observed, ensure_ascii=False),
        "expected": json.dumps(expected, ensure_ascii=False),
    }


def _validate(config: dict[str, Any], environment: dict[str, Any]) -> list[dict[str, str]]:
    project_cfg = config["project"]
    runtime_cfg = config["runtime"]
    git_cfg = config["git"]
    git = environment["git"]

    distribution_name = str(project_cfg["distribution_name"])
    dist_version = installed_distribution_version(distribution_name)
    required_packages = list(runtime_cfg.get("required_packages", []))
    missing_packages = [
        package for package in required_packages if installed_distribution_version(package) is None
    ]

    python_version = str(environment["python"]["version"])
    expected_python = str(runtime_cfg["python_major_minor"])

    checks = [
        _check(
            "python_major_minor",
            ".".join(python_version.split(".")[:2]),
            expected_python,
            python_version.startswith(expected_python + "."),
        ),
        _check(
            "virtual_environment_active",
            environment["python"]["virtual_environment_active"],
            True,
            bool(environment["python"]["virtual_environment_active"]),
        ),
        _check(
            "distribution_installed",
            {"name": distribution_name, "version": dist_version},
            {"name": distribution_name, "version": project_cfg["expected_version"]},
            dist_version == str(project_cfg["expected_version"]),
        ),
        _check("required_packages", missing_packages, [], not missing_packages),
        _check("git_repository", git.get("is_repository"), True, git.get("is_repository") is True),
    ]

    if git.get("is_repository"):
        expected_branch = str(git_cfg["expected_branch"])
        checks.append(_check("git_branch", git.get("branch"), expected_branch, git.get("branch") == expected_branch))
        if git_cfg.get("require_clean_worktree", False):
            checks.append(
                _check("git_clean_worktree", git.get("clean_worktree"), True, git.get("clean_worktree") is True)
            )
        if git_cfg.get("require_upstream", False):
            checks.append(_check("git_upstream", git.get("upstream"), "configured", bool(git.get("upstream"))))
        if git_cfg.get("require_upstream_sync", False):
            sync = {"ahead": git.get("ahead"), "behind": git.get("behind")}
            checks.append(_check("git_upstream_sync", sync, {"ahead": 0, "behind": 0}, sync == {"ahead": 0, "behind": 0}))

    return checks


def _write_checksums(out_dir: Path) -> None:
    candidates = sorted(path for path in out_dir.iterdir() if path.is_file() and path.name != "checksums.sha256")
    lines = [f"{sha256_file(path)}  {path.name}" for path in candidates]
    (out_dir / "checksums.sha256").write_text("\n".join(lines) + "\n", encoding="utf-8")


def run_r0(config_path: Path, out_dir: Path) -> int:
    timer = Timer.start()
    config_path = config_path.resolve()
    out_dir = out_dir.resolve()
    out_dir.mkdir(parents=True, exist_ok=False)

    config = _load_config(config_path)
    project_root = _project_root_from_config(config_path)
    capture_cfg = config.get("capture", {})

    shutil.copy2(config_path, out_dir / "config_snapshot.yaml")

    environment = collect_environment(
        project_root,
        include_hostname=bool(capture_cfg.get("include_hostname", False)),
        include_remote_urls=bool(capture_cfg.get("include_remote_urls", False)),
        env_allowlist=list(capture_cfg.get("environment_variables_allowlist", [])),
    )
    write_json(out_dir / "environment.json", environment)

    if capture_cfg.get("include_all_python_distributions", True):
        write_csv(
            out_dir / "python_packages.csv",
            python_distributions(),
            ["name", "version"],
        )

    if capture_cfg.get("include_pip_freeze", True):
        freeze_code, freeze_out, freeze_err = pip_freeze()
        (out_dir / "pip_freeze.txt").write_text(freeze_out + "\n", encoding="utf-8")
        if freeze_code != 0:
            (out_dir / "pip_freeze_error.txt").write_text(freeze_err + "\n", encoding="utf-8")

    validation = _validate(config, environment)
    write_csv(out_dir / "r0_validation.csv", validation, ["check", "status", "observed", "expected"])
    overall = "PASS" if all(row["status"] == "PASS" for row in validation) else "FAIL"

    performance = [{"step": "R0_TOTAL", "wall_seconds": f"{timer.elapsed():.6f}"}]
    write_csv(out_dir / "performance.csv", performance, ["step", "wall_seconds"])

    manifest = {
        "schema_version": "simfleet-studio-edg-r0-manifest-v1",
        "phase_id": config["phase_id"],
        "work_package": config["work_package"],
        "status": overall,
        "git_commit": environment.get("git", {}).get("commit"),
        "config_sha256": sha256_file(out_dir / "config_snapshot.yaml"),
        "files": sorted(path.name for path in out_dir.iterdir() if path.is_file()) + ["checksums.sha256"],
    }
    write_json(out_dir / "manifest.json", manifest)

    log_lines = [
        "SimFleet Studio EDG - R0 Environment",
        f"status={overall}",
        f"git_commit={manifest['git_commit']}",
        f"python={environment['python']['version']}",
        f"interpreter={environment['python']['executable']}",
    ]
    (out_dir / "run.log").write_text("\n".join(log_lines) + "\n", encoding="utf-8")

    _write_checksums(out_dir)
    print(json.dumps({"status": overall, "output": str(out_dir)}, indent=2))
    return 0 if overall == "PASS" else 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run PRE-F3 R0 environment capture")
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    raise SystemExit(run_r0(args.config, args.out))


if __name__ == "__main__":
    main()
