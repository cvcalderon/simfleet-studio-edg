"""Verify local C-IMPL-01 packaging/layout; no source data or science touched."""

import json
import platform
import subprocess
import sys
from pathlib import Path

import simfleet_edg


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    checks = {
        "python_3_12": sys.version_info[:2] == (3, 12),
        "project_layout": all(
            (root / path).exists()
            for path in ["pyproject.toml", "README.md", "src/simfleet_edg", "tests",
                         "configs", "notebooks", "data", "artifacts"]
        ),
        "package_import": simfleet_edg.__version__ == "0.0.1",
        "git_initialized": (root / ".git").exists(),
        "venv_active": sys.prefix != sys.base_prefix,
    }
    cp = subprocess.run(["git", "status", "--short"], cwd=root,
                        check=False, capture_output=True, text=True)
    result = {
        "status": "PASS" if all(checks.values()) else "INCOMPLETE",
        "checks": checks,
        "python": sys.version.split()[0],
        "interpreter": sys.executable,
        "platform": platform.platform(),
        "git_status_available": cp.returncode == 0,
        "git_status_short": cp.stdout.strip() if cp.returncode == 0 else None,
        "note": "Bootstrap check only. R0 environment capture is a separate task.",
    }
    print(json.dumps(result, indent=2, ensure_ascii=False))
    if not all(checks.values()):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
