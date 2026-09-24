"""Verify C-IMPL-02 prerequisites before committing and running official R0."""

from __future__ import annotations

import importlib.metadata
import json
import subprocess
import sys
from pathlib import Path

EXPECTED_KERNEL = "simfleet-studio-edg-py312"
REQUIRED = [
    "numpy", "pandas", "pyarrow", "PyYAML", "pydantic", "jupyterlab", "ipykernel",
    "matplotlib", "pytest", "pytest-cov", "ruff", "mypy",
]


def installed(name: str) -> bool:
    try:
        importlib.metadata.version(name)
        return True
    except importlib.metadata.PackageNotFoundError:
        return False


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    missing = [name for name in REQUIRED if not installed(name)]
    kernel_proc = subprocess.run(
        [sys.executable, "-m", "jupyter", "kernelspec", "list", "--json"],
        check=False,
        capture_output=True,
        text=True,
    )
    kernel_present = False
    if kernel_proc.returncode == 0:
        payload = json.loads(kernel_proc.stdout)
        kernel_present = EXPECTED_KERNEL in payload.get("kernelspecs", {})

    result = {
        "status": "PASS" if not missing and kernel_present else "FAIL",
        "python": sys.version.split()[0],
        "interpreter": sys.executable,
        "project_root": str(root),
        "missing_packages": missing,
        "expected_kernel": EXPECTED_KERNEL,
        "kernel_present": kernel_present,
    }
    print(json.dumps(result, indent=2))
    return 0 if result["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
