from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from simfleet_edg.evaluation.participation_cal_real import (
    _apply_sigmoid,
    _fit_sigmoid,
    _guardrail_metrics,
    load_authorization,
)


def _frame() -> pd.DataFrame:
    rows = []
    for household in range(40):
        rows.append(
            {
                "source_household_id_target": str(household),
                "source_person_id_target": str(1000 + household),
                "target_trip_day": household % 3 != 0,
                "fit_weight_P_GEW_target": 1.0 + (household % 5) / 10,
                "age_infr_class": "A" if household < 20 else "B",
                "sex": "FEMALE" if household % 2 else "MALE",
                "primary_activity_status": (
                    "WORK" if household < 30 else "OTHER"
                ),
                "household_size_class": "1" if household < 20 else "2",
            }
        )
    return pd.DataFrame(rows)


def test_sigmoid_fit_produces_finite_probabilities() -> None:
    observed = np.array([0, 0, 1, 1, 1, 0], dtype=int)
    probability = np.array([0.1, 0.3, 0.55, 0.7, 0.9, 0.4])
    weights = np.ones(len(observed))
    intercept, slope = _fit_sigmoid(probability, observed, weights)
    calibrated = _apply_sigmoid(probability, intercept, slope)
    assert np.isfinite([intercept, slope]).all()
    assert ((calibrated > 0) & (calibrated < 1)).all()


def test_guardrail_metrics_uses_32_replicates_and_supported_cells() -> None:
    frame = _frame()
    probability = np.linspace(0.2, 0.9, len(frame))
    uniforms = np.tile(np.linspace(0.01, 0.99, len(frame)), (32, 1))
    summary, conditional, draws = _guardrail_metrics(
        frame,
        probability,
        uniforms,
    )
    assert draws.shape == (32, len(frame))
    assert summary["m2_cond_01_supported_cells"] >= 1
    assert set(conditional["support_status"]).issubset({"OK", "LOW_N"})


def _authorization(commit: str, *, test_open: bool = False) -> dict:
    return {
        "phase": "F3.4b-2b",
        "authorized_implementation_commit": commit,
        "component": "DG_PARTICIPATION",
        "real_cal_open_authorized": True,
        "allowed_cal_files": ["person_day_context.csv", "participation.csv"],
        "candidate_artifacts": 8,
        "candidate_selection_at_entry": "NONE",
        "test_open_authorized": test_open,
        "formal_g2": "NOT_EVALUATED",
    }


def test_authorization_rejects_wrong_commit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    authorization = tmp_path / "auth.json"
    authorization.write_text(json.dumps(_authorization("wrong")))

    def fake_git(root: Path, *args: str) -> str:
        del root
        if args == ("rev-parse", "HEAD"):
            return "actual"
        return ""

    monkeypatch.setattr(
        "simfleet_edg.evaluation.participation_cal_real._git",
        fake_git,
    )
    with pytest.raises(PermissionError, match="not bound"):
        load_authorization(authorization, tmp_path)


def test_authorization_rejects_test_open(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    authorization = tmp_path / "auth.json"
    authorization.write_text(json.dumps(_authorization("abc", test_open=True)))

    def fake_git(root: Path, *args: str) -> str:
        del root
        if args == ("rev-parse", "HEAD"):
            return "abc"
        return ""

    monkeypatch.setattr(
        "simfleet_edg.evaluation.participation_cal_real._git",
        fake_git,
    )
    with pytest.raises(PermissionError, match="test_open_authorized"):
        load_authorization(authorization, tmp_path)


def test_authorization_accepts_exact_clean_main(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    authorization = tmp_path / "auth.json"
    authorization.write_text(json.dumps(_authorization("abc")))

    def fake_git(root: Path, *args: str) -> str:
        del root
        responses = {
            ("rev-parse", "HEAD"): "abc",
            ("status", "--porcelain"): "",
            ("branch", "--show-current"): "main",
            ("rev-list", "--count", "origin/main..HEAD"): "0",
            ("rev-list", "--count", "HEAD..origin/main"): "0",
        }
        return responses[args]

    monkeypatch.setattr(
        "simfleet_edg.evaluation.participation_cal_real._git",
        fake_git,
    )
    payload = load_authorization(authorization, tmp_path)
    assert payload["authorized_implementation_commit"] == "abc"
