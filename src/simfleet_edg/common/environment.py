"""Environment inspection helpers used by PRE-F3 reproducibility runs."""

from __future__ import annotations

import csv
import hashlib
import importlib.metadata
import json
import os
import platform
import shutil
import subprocess
import sys
import time
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def _run(command: list[str], cwd: Path | None = None) -> tuple[int, str, str]:
    result = subprocess.run(
        command,
        cwd=cwd,
        check=False,
        capture_output=True,
        text=True,
    )
    return result.returncode, result.stdout.strip(), result.stderr.strip()


def _read_key_value_file(path: Path, separator: str = "=") -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if separator not in line:
            continue
        key, value = line.split(separator, 1)
        values[key.strip()] = value.strip().strip('"')
    return values


def _linux_cpu_model() -> str | None:
    cpuinfo = Path("/proc/cpuinfo")
    if not cpuinfo.exists():
        return platform.processor() or None
    for line in cpuinfo.read_text(encoding="utf-8", errors="replace").splitlines():
        if line.lower().startswith("model name") and ":" in line:
            return line.split(":", 1)[1].strip()
    return platform.processor() or None


def _linux_memory_total_bytes() -> int | None:
    meminfo = _read_key_value_file(Path("/proc/meminfo"), separator=":")
    raw = meminfo.get("MemTotal")
    if not raw:
        return None
    parts = raw.split()
    try:
        value = int(parts[0])
    except (ValueError, IndexError):
        return None
    unit = parts[1].lower() if len(parts) > 1 else "kb"
    multiplier = {"kb": 1024, "mb": 1024**2, "gb": 1024**3}.get(unit, 1)
    return value * multiplier


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def python_distributions() -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for dist in importlib.metadata.distributions():
        name = dist.metadata.get("Name") or "UNKNOWN"
        rows.append({"name": name, "version": dist.version})
    return sorted(rows, key=lambda row: row["name"].lower())


def installed_distribution_version(name: str) -> str | None:
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return None


def git_info(project_root: Path, include_remote_urls: bool = False) -> dict[str, Any]:
    code, root, _ = _run(["git", "rev-parse", "--show-toplevel"], cwd=project_root)
    if code != 0:
        return {"is_repository": False}

    git_root = Path(root)
    _, commit, _ = _run(["git", "rev-parse", "HEAD"], cwd=git_root)
    _, branch, _ = _run(["git", "branch", "--show-current"], cwd=git_root)
    _, short_status, _ = _run(["git", "status", "--short"], cwd=git_root)
    upstream_code, upstream, _ = _run(
        ["git", "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"],
        cwd=git_root,
    )

    ahead: int | None = None
    behind: int | None = None
    if upstream_code == 0:
        counts_code, counts, _ = _run(
            ["git", "rev-list", "--left-right", "--count", "HEAD...@{u}"],
            cwd=git_root,
        )
        if counts_code == 0:
            fields = counts.split()
            if len(fields) == 2:
                ahead, behind = int(fields[0]), int(fields[1])

    remotes_code, remotes_text, _ = _run(["git", "remote"], cwd=git_root)
    remotes = sorted(remotes_text.splitlines()) if remotes_code == 0 and remotes_text else []

    info: dict[str, Any] = {
        "is_repository": True,
        "root": str(git_root),
        "commit": commit,
        "branch": branch,
        "clean_worktree": not bool(short_status),
        "status_short": short_status,
        "upstream": upstream if upstream_code == 0 else None,
        "ahead": ahead,
        "behind": behind,
        "remotes": remotes,
    }

    if include_remote_urls:
        remote_urls: dict[str, dict[str, str | None]] = {}
        for remote in remotes:
            _, fetch_url, _ = _run(["git", "remote", "get-url", remote], cwd=git_root)
            push_code, push_url, _ = _run(
                ["git", "remote", "get-url", "--push", remote], cwd=git_root
            )
            remote_urls[remote] = {
                "fetch": fetch_url or None,
                "push": push_url if push_code == 0 and push_url else None,
            }
        info["remote_urls"] = remote_urls

    return info


def collect_environment(
    project_root: Path,
    *,
    include_hostname: bool = False,
    include_remote_urls: bool = False,
    env_allowlist: Iterable[str] = (),
) -> dict[str, Any]:
    project_root = project_root.resolve()
    os_release = _read_key_value_file(Path("/etc/os-release"))
    disk = shutil.disk_usage(project_root)

    affinity: list[int] | None = None
    if hasattr(os, "sched_getaffinity"):
        affinity = sorted(os.sched_getaffinity(0))

    result: dict[str, Any] = {
        "schema_version": "simfleet-studio-edg-r0-environment-v1",
        "captured_at_utc": datetime.now(UTC).isoformat(),
        "project_root": str(project_root),
        "system": {
            "platform": platform.platform(),
            "system": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
            "os_release": {
                "id": os_release.get("ID"),
                "version_id": os_release.get("VERSION_ID"),
                "pretty_name": os_release.get("PRETTY_NAME"),
            },
        },
        "python": {
            "version": platform.python_version(),
            "implementation": platform.python_implementation(),
            "executable": sys.executable,
            "prefix": sys.prefix,
            "base_prefix": sys.base_prefix,
            "virtual_environment_active": sys.prefix != sys.base_prefix,
        },
        "hardware": {
            "cpu_model": _linux_cpu_model(),
            "logical_cpus": os.cpu_count(),
            "cpu_affinity": affinity,
            "memory_total_bytes": _linux_memory_total_bytes(),
        },
        "storage": {
            "path": str(project_root),
            "total_bytes": disk.total,
            "used_bytes": disk.used,
            "free_bytes": disk.free,
        },
        "git": git_info(project_root, include_remote_urls=include_remote_urls),
        "environment_variables": {key: os.environ.get(key) for key in env_allowlist},
    }
    if include_hostname:
        result["system"]["hostname"] = platform.node()
    return result


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def pip_freeze() -> tuple[int, str, str]:
    return _run([sys.executable, "-m", "pip", "freeze"])


@dataclass(frozen=True)
class Timer:
    started: float

    @classmethod
    def start(cls) -> Timer:
        return cls(time.perf_counter())

    def elapsed(self) -> float:
        return time.perf_counter() - self.started
