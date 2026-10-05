from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from simfleet_edg.population.calibration_evaluation import stock_category
from simfleet_edg.repro import f1_pconstr_cal01_runner as runner


def test_stock_classes_are_frozen() -> None:
    assert stock_category(0, cap=3) == "ZERO"
    assert stock_category(3, cap=3) == "THREE_PLUS"
    assert stock_category(2, cap=10) == "TWO_TO_NINE"
    assert stock_category(10, cap=10) == "TEN_PLUS"


def test_expand_bootstrap_preserves_household_multiplicity() -> None:
    frame = pd.DataFrame({"source_household_id": ["1", "1", "2"], "x": [1, 2, 3]})
    out = runner._expand_by_households(frame, ["1", "2", "1"])
    assert out["source_household_id"].tolist() == ["1", "1", "2", "1", "1"]


def test_execution_authorization_negative_fails_before_inputs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    auth = tmp_path / "auth.json"
    auth.write_text(json.dumps({
        "schema_version": "simfleet-edg-f1-pconstr-cal01-execution-authorization-v1",
        "phase_id": "F1-P_CONSTR-CAL-01",
        "authorized": False,
    }), encoding="utf-8")
    monkeypatch.setattr(runner, "repository_state", lambda _: {
        "branch": "main", "head": "abc", "origin_main": "abc", "porcelain": ""
    })
    with pytest.raises(runner.AuthorizationError):
        runner.validate_execution_authorization(auth, repo, impl03_expected_sha256="x")


def test_execution_authorization_positive_exact(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    auth = tmp_path / "auth.json"
    payload = {
        "schema_version": "simfleet-edg-f1-pconstr-cal01-execution-authorization-v1",
        "phase_id": "F1-P_CONSTR-CAL-01",
        "authorized": True,
        "authorization_status": "AUTHORIZED_A1",
        "protocol_authorization_commit": runner.PROTOCOL_AUTH_COMMIT,
        "authorized_runner_commit": "abc",
        "allowed_partition": "CALIBRATION_ONLY",
        "cal_open_authorized": True,
        "impl03_runbundle_sha256": "ziphash",
        "candidate_selection_at_entry": "NONE",
        "g1_thresholds_before_run": "NOT_FROZEN",
        "mid_test_open_authorized": False,
        "holdout_1000A_1035_open_authorized": False,
        "plr_allocation_authorized": False,
        "f3_modification_authorized": False,
    }
    auth.write_text(json.dumps(payload), encoding="utf-8")
    monkeypatch.setattr(runner, "repository_state", lambda _: {
        "branch": "main", "head": "abc", "origin_main": "abc", "porcelain": ""
    })
    result = runner.validate_execution_authorization(auth, repo, impl03_expected_sha256="ziphash")
    assert result["repository_head"] == "abc"


def test_selective_csv_only_materializes_allowed_rows(tmp_path: Path) -> None:
    path = tmp_path / "x.csv"
    path.write_text('"H_ID","VALUE"\n1,"secret-a"\n2,"allowed"\n3,"secret-b"\n', encoding="utf-8")
    out = runner.selective_csv_rows(
        path,
        allowed_household_ids={"2"},
        household_id_index=0,
        required_columns=["H_ID", "VALUE"],
    )
    assert out.to_dict("records") == [{"H_ID": "2", "VALUE": "allowed"}]


def test_primary_family_universe_frozen() -> None:
    assert runner.PRIMARY_FAMILIES == (
        "ACTIVITY_BY_AGE",
        "LICENSE_BY_AGE_SEX",
        "HH_CAR_STOCK_BY_SIZE",
        "HH_BIKE_EBIKE_STOCK_BY_SIZE",
    )


def test_candidate_universe_frozen() -> None:
    assert runner.VARIANTS == (
        "P_TRS_V1_FINAL",
        "P_CONSTR_RMIN_V2_HD_U",
        "P_CONSTR_RMIN_V2_HD_W",
    )
