from __future__ import annotations

import argparse
import importlib
import json
import subprocess
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXPECTED_PARENT = "1fe196a5495b5d9e0952273a4ebab3840e7aaca9"
EXPECTED = {
    "scipy": ">=1.16,<2",
    "scikit-learn": ">=1.7,<2",
    "statsmodels": ">=0.14.5,<1",
    "lightgbm": ">=4.6,<5",
}
IMPORTS = {
    "scipy": "scipy",
    "scikit-learn": "sklearn",
    "statsmodels": "statsmodels",
    "lightgbm": "lightgbm",
}


def _gitignore_has(line: str) -> bool:
    lines = (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
    return line in lines


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--require-runtime", action="store_true")
    args = parser.parse_args()

    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    modeling = pyproject["project"]["optional-dependencies"].get("modeling", [])
    modeling_map = {item.split(">=", 1)[0]: item[len(item.split(">=", 1)[0]) :] for item in modeling}

    parent_is_ancestor = (
        subprocess.run(
            ["git", "merge-base", "--is-ancestor", EXPECTED_PARENT, "HEAD"],
            cwd=ROOT,
            check=False,
        ).returncode
        == 0
    )
    model_data = ROOT / "artifacts/model_data/F3_2a_training_data_v1"

    checks: dict[str, bool] = {
        "parent_implementation_ancestor": parent_is_ancestor,
        "f3_2b_materialized_data_present": (model_data / "materialization_manifest.json").is_file(),
        "test_absent_in_materialized_data": not (model_data / "TEST").exists(),
        "python_312": sys.version_info[:2] == (3, 12),
        "modeling_group_present": bool(modeling),
        "modeling_four_exact": set(modeling_map) == set(EXPECTED),
        "scipy_declared": modeling_map.get("scipy") == EXPECTED["scipy"],
        "sklearn_declared": modeling_map.get("scikit-learn") == EXPECTED["scikit-learn"],
        "statsmodels_declared": modeling_map.get("statsmodels") == EXPECTED["statsmodels"],
        "lightgbm_declared": modeling_map.get("lightgbm") == EXPECTED["lightgbm"],
        "model_data_ignored": _gitignore_has("/artifacts/model_data/*"),
        "environment_snapshots_ignored": _gitignore_has("/artifacts/environment/*"),
        "test_not_mentioned_as_generated_output": not (ROOT / ".gitignore").read_text(encoding="utf-8").find("/artifacts/model_data/TEST") >= 0,
    }

    runtime: dict[str, dict[str, str | bool]] = {}
    for package, module_name in IMPORTS.items():
        try:
            module = importlib.import_module(module_name)
            runtime[package] = {
                "available": True,
                "version": str(getattr(module, "__version__", "UNKNOWN")),
            }
        except Exception as exc:  # noqa: BLE001 - verifier must report import failures
            runtime[package] = {
                "available": False,
                "version": "MISSING",
                "error": f"{type(exc).__name__}: {exc}",
            }

    runtime_all = all(bool(item["available"]) for item in runtime.values())
    checks["runtime_modeling_stack_available"] = runtime_all if args.require_runtime else True

    declaration_ok = all(value for key, value in checks.items() if key != "runtime_modeling_stack_available")
    status = "PASS" if declaration_ok and (runtime_all or not args.require_runtime) else "FAIL"
    phase = "RUNTIME" if args.require_runtime else "DECLARATION"

    print(
        json.dumps(
            {
                "status": status,
                "phase": phase,
                "expected_parent_commit": EXPECTED_PARENT,
                "checks": checks,
                "runtime": runtime,
            },
            indent=2,
            sort_keys=True,
        )
    )
    if status != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
