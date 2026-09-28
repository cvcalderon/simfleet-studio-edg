from __future__ import annotations

import importlib.util
from pathlib import Path

import pandas as pd

SCRIPT = Path("scripts/verify_f3_4c2_runbundle.py")


def _module():
    spec = importlib.util.spec_from_file_location("f3_4c2_runbundle_verifier", SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_read_csv_allow_empty_returns_typed_empty_frame(tmp_path: Path):
    module = _module()
    path = tmp_path / "empty.csv"
    path.write_text("\n", encoding="utf-8")

    frame = module.read_csv_allow_empty(path, ["a", "b"])

    assert frame.empty
    assert list(frame.columns) == ["a", "b"]


def test_zero_family_winners_means_zero_decision_rows():
    module = _module()
    grid = pd.DataFrame(
        {
            "artifact_id": ["a", "b", "c", "d"],
            "selected_within_family": [False, False, False, False],
        }
    )

    assert module.expected_decision_rows(grid) == 0


def test_selected_family_winners_define_decision_count():
    module = _module()
    grid = pd.DataFrame(
        {
            "artifact_id": ["a", "b", "c", "d"],
            "selected_within_family": [True, False, False, True],
        }
    )

    assert module.expected_decision_rows(grid) == 2
