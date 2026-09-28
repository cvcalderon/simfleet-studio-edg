from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from simfleet_edg.evaluation.trip_count_cal_preopen import (
    BOOTSTRAPS,
    REPLICATES,
    load_preopen_config,
    run_synthetic_trip_count_preopen,
)
from simfleet_edg.evaluation.trip_count_cal_real import load_authorization

ROOT = Path.cwd()
CFG = ROOT / "configs/f3/f3_4c2a_trip_count_real_cal_preopen_v1.yaml"


def test_preopen_contract_keeps_trip_count_cal_and_test_closed():
    cfg = load_preopen_config(CFG)
    assert cfg["preopen"]["new_trip_count_cal_rows_read"] == 0
    assert cfg["preopen"]["test_rows_read"] == 0
    assert cfg["preopen"]["candidate_selection"] == "NONE"
    assert cfg["preopen"]["real_trip_count_cal_open_authorized"] is False
    assert cfg["preopen"]["test_open_authorized"] is False
    assert cfg["preopen"]["formal_g2"] == "NOT_EVALUATED"


def test_replicates_and_bootstrap_frozen():
    cfg = load_preopen_config(CFG)
    assert cfg["evaluation"]["stochastic_replicates"] == REPLICATES == 32
    assert cfg["evaluation"]["household_bootstrap_replicates"] == BOOTSTRAPS == 1000


def test_synthetic_preopen_bundle_reads_no_cal(tmp_path: Path):
    out = tmp_path / "run"
    manifest = run_synthetic_trip_count_preopen(
        ROOT,
        out,
        validate_artifacts=False,
    )
    assert manifest["status"] == "PASS"
    assert manifest["candidate_artifacts"] == 5
    assert manifest["candidate_selection"] == "NONE"
    assert manifest["new_trip_count_cal_rows_read"] == 0
    assert manifest["test_rows_read"] == 0
    access = json.loads((out / "cal_access_manifest.json").read_text())
    assert access["cal_files_opened"] == []
    assert access["test_files_opened"] == []


def test_synthetic_primary_metrics_cover_five_candidates(tmp_path: Path):
    out = tmp_path / "run"
    run_synthetic_trip_count_preopen(ROOT, out, validate_artifacts=False)
    frame = pd.read_csv(out / "primary_metrics.csv")
    assert len(frame) == 5
    assert frame["artifact_id"].nunique() == 5
    assert set(frame["metric"]) == {"WEIGHTED_DISCRETE_CRPS_ON_K"}


def test_synthetic_modes_exercise_isolated_and_propagated(tmp_path: Path):
    out = tmp_path / "run"
    run_synthetic_trip_count_preopen(ROOT, out, validate_artifacts=False)
    modes = pd.read_csv(out / "mode_validation.csv")
    assert set(modes["mode"]) == {"ISOLATED", "PROPAGATED"}
    assert set(modes["status"]) == {"PASS"}


def test_real_authorization_rejects_unapproved_template(tmp_path: Path):
    payload = {
        "phase": "F3.4c-2b",
        "component": "DG_TRIP_COUNT",
        "authorized_implementation_commit": "WRONG",
        "real_trip_count_cal_open_authorized": False,
        "candidate_artifacts": 5,
        "candidate_selection_at_entry": "NONE",
        "allowed_cal_files": [
            "person_day_context.csv",
            "participation.csv",
            "trip_count.csv",
        ],
        "test_open_authorized": False,
        "formal_g2": "NOT_EVALUATED",
    }
    path = tmp_path / "auth.json"
    path.write_text(json.dumps(payload))
    with pytest.raises(PermissionError):
        load_authorization(path, ROOT)


def test_real_runner_requires_three_exact_cal_files():
    text = (
        ROOT / "src/simfleet_edg/evaluation/trip_count_cal_real.py"
    ).read_text(encoding="utf-8")
    assert '"person_day_context.csv"' in text
    assert '"participation.csv"' in text
    assert '"trip_count.csv"' in text
    assert "real_trip_count_cal_open_authorized" in text
