from __future__ import annotations

import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _modeling() -> list[str]:
    data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    return data["project"]["optional-dependencies"]["modeling"]


def test_modeling_group_has_four_dependencies() -> None:
    assert len(_modeling()) == 4


def test_scipy_declared() -> None:
    assert "scipy>=1.16,<2" in _modeling()


def test_scikit_learn_declared() -> None:
    assert "scikit-learn>=1.7,<2" in _modeling()


def test_statsmodels_declared() -> None:
    assert "statsmodels>=0.14.5,<1" in _modeling()


def test_lightgbm_declared() -> None:
    assert "lightgbm>=4.6,<5" in _modeling()


def test_model_data_is_ignored() -> None:
    text = (ROOT / ".gitignore").read_text(encoding="utf-8")
    assert "/artifacts/model_data/*" in text


def test_environment_snapshots_are_ignored() -> None:
    text = (ROOT / ".gitignore").read_text(encoding="utf-8")
    assert "/artifacts/environment/*" in text


def test_existing_reproduction_group_is_unchanged() -> None:
    data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert data["project"]["optional-dependencies"]["reproduction"] == [
        "numpy>=1.26,<3",
        "pandas>=2.2,<3",
        "pyarrow>=17,<24",
        "PyYAML>=6,<7",
        "pydantic>=2.8,<3",
    ]
