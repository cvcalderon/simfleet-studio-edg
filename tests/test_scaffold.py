"""C-IMPL-01 smoke tests only; scientific invariants begin in R1/R2."""

from importlib.metadata import version
from pathlib import Path

import simfleet_edg


def test_importable() -> None:
    assert simfleet_edg.__version__ == "0.0.1"


def test_installed_distribution() -> None:
    assert version("simfleet-studio-edg") == simfleet_edg.__version__


def test_scientific_source_is_empty_skeleton() -> None:
    root = Path(simfleet_edg.__file__).parent
    expected = {"canonical", "population", "demand", "evaluation", "common"}
    assert all((root / sub / "__init__.py").exists() for sub in expected)
