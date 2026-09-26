from __future__ import annotations

import hashlib
import importlib
import json
import platform
import subprocess
import sys
from pathlib import Path

PACKAGES = {
    "numpy": "numpy",
    "pandas": "pandas",
    "scipy": "scipy",
    "scikit-learn": "sklearn",
    "statsmodels": "statsmodels",
    "lightgbm": "lightgbm",
}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: python scripts/capture_f3_2c_env.py <output-dir>")
    out = Path(sys.argv[1])
    if out.exists():
        raise SystemExit(f"output already exists: {out}")
    out.mkdir(parents=True)

    versions: dict[str, str] = {}
    for package, module_name in PACKAGES.items():
        module = importlib.import_module(module_name)
        versions[package] = str(getattr(module, "__version__", "UNKNOWN"))

    freeze = subprocess.run(
        [sys.executable, "-m", "pip", "freeze"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    freeze_path = out / "pip_freeze.txt"
    freeze_path.write_text(freeze, encoding="utf-8")

    git_commit = subprocess.run(
        ["git", "rev-parse", "HEAD"], check=True, capture_output=True, text=True
    ).stdout.strip()

    manifest = {
        "snapshot_id": "F3_2C_MODELING_ENVIRONMENT_V1",
        "git_commit": git_commit,
        "python": sys.version,
        "platform": platform.platform(),
        "packages": versions,
        "test_partition_consumed": False,
        "scientific_design_changed": False,
    }
    manifest_path = out / "environment_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    checksum_path = out / "checksums.sha256"
    checksum_path.write_text(
        f"{sha256(manifest_path)}  environment_manifest.json\n"
        f"{sha256(freeze_path)}  pip_freeze.txt\n",
        encoding="utf-8",
    )
    print(json.dumps({"status": "PASS", "output": str(out), "packages": versions}, indent=2))


if __name__ == "__main__":
    main()
