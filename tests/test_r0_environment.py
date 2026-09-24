"""Unit tests for R0 environment inspection helpers."""

from pathlib import Path

from simfleet_edg.common.environment import collect_environment, python_distributions


def test_collect_environment_has_required_sections() -> None:
    root = Path.cwd()
    result = collect_environment(root)
    assert result["schema_version"] == "simfleet-studio-edg-r0-environment-v1"
    assert {"system", "python", "hardware", "storage", "git"} <= result.keys()
    assert result["python"]["executable"]


def test_python_distributions_are_sorted() -> None:
    rows = python_distributions()
    names = [row["name"].lower() for row in rows]
    assert names == sorted(names)
    assert all(row["name"] and row["version"] for row in rows)
