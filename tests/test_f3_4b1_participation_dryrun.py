from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from simfleet_edg.evaluation.participation_cal_dryrun import (
    EXPECTED_BOOTSTRAPS,
    EXPECTED_REPLICATES,
    _candidate_rows,
    _synthetic_cases,
    load_dryrun_config,
    run_synthetic_participation_dryrun,
)

ROOT = Path.cwd()
CFG = ROOT / "configs/f3/f3_4b1_participation_cal_runner_dryrun_v1.yaml"


def test_contract_keeps_cal_and_test_closed():
    config = load_dryrun_config(CFG)
    assert config["execution_mode"] == "SYNTHETIC_DRYRUN_ONLY"
    assert config["cal_partition"] == "UNOPENED"
    assert config["cal_rows_read"] == 0
    assert config["test_partition"] == "SEALED"
    assert config["test_rows_read"] == 0
    assert config["candidate_selection"] == "NONE"


def test_replicates_and_bootstrap_are_frozen():
    config = load_dryrun_config(CFG)
    assert config["stochastic_replicates"] == EXPECTED_REPLICATES == 32
    assert config["household_bootstrap_replicates"] == EXPECTED_BOOTSTRAPS == 1000


def test_candidate_plan_is_participation_only_and_exact_8():
    rows = _candidate_rows(ROOT, ROOT / "docs/F3_4A_CANDIDATE_EXECUTION_PLAN_v1.csv")
    assert len(rows) == 8
    assert set(rows["component"]) == {"DG_PARTICIPATION"}
    assert set(rows["train_state_required"]) == {"FITTED_TRAIN_ONLY_NOT_SELECTED"}


def test_synthetic_cases_have_household_clusters():
    frame = _synthetic_cases()
    assert len(frame) == 24
    assert frame["source_household_id"].nunique() == 12
    assert set(frame["observed_trip_day"]).issubset({0, 1})
    assert (frame["weight"] > 0).all()


def test_dryrun_produces_required_bundle_without_cal(tmp_path: Path):
    out = tmp_path / "run"
    manifest = run_synthetic_participation_dryrun(ROOT, out, validate_frozen_artifacts=False)
    assert manifest["status"] == "PASS"
    assert manifest["execution_mode"] == "SYNTHETIC_DRYRUN_ONLY"
    assert manifest["cal_rows_read"] == 0
    assert manifest["test_rows_read"] == 0
    assert manifest["candidate_selection"] == "NONE"
    required = {
        "run_manifest.json",
        "execution_contract_snapshot.yaml",
        "environment.json",
        "cal_access_manifest.json",
        "input_hash_validation.csv",
        "candidate_artifact_validation.csv",
        "primary_metrics.csv",
        "guardrails.csv",
        "bootstrap_intervals.csv",
        "grid_selection.csv",
        "promotion_decisions.csv",
        "validation.csv",
        "performance.json",
        "issues.csv",
        "part_b_calibration_decision.json",
        "selected_component_artifact.json",
        "checksums.sha256",
    }
    assert {p.name for p in out.iterdir()} == required
    access = json.loads((out / "cal_access_manifest.json").read_text())
    assert access["cal_files_opened"] == []
    assert access["test_files_opened"] == []
    selected = json.loads((out / "selected_component_artifact.json").read_text())
    assert selected["candidate_selection"] == "NONE"
    assert selected["authorized_for_downstream"] is False


def test_primary_metrics_cover_exact_eight_artifacts(tmp_path: Path):
    out = tmp_path / "run"
    run_synthetic_participation_dryrun(ROOT, out, validate_frozen_artifacts=False)
    metrics = pd.read_csv(out / "primary_metrics.csv")
    assert len(metrics) == 8
    assert metrics["artifact_id"].nunique() == 8
    assert set(metrics["metric"]) == {"WEIGHTED_BERNOULLI_LOG_LOSS"}
    assert set(metrics["data_source"]) == {"SYNTHETIC_ONLY"}


def test_bootstrap_exercises_two_sequential_promotions(tmp_path: Path):
    out = tmp_path / "run"
    run_synthetic_participation_dryrun(ROOT, out, validate_frozen_artifacts=False)
    boot = pd.read_csv(out / "bootstrap_intervals.csv")
    promotions = pd.read_csv(out / "promotion_decisions.csv")
    assert list(boot["stage"]) == ["REFERENCE_TO_A", "INCUMBENT_TO_B"]
    assert len(promotions) == 2
    assert set(promotions["dryrun_only"].astype(str).str.lower()) <= {"true"}


def test_invalid_mode_cannot_be_loaded(tmp_path: Path):
    bad = tmp_path / "bad.yaml"
    bad.write_text("phase: F3.4b-1\nexecution_mode: REAL_CAL\ncal_rows_read: 0\ntest_rows_read: 0\n")
    with pytest.raises(ValueError):
        load_dryrun_config(bad)


def test_runner_source_contains_no_calibration_or_test_reader_literal():
    source = (ROOT / "src/simfleet_edg/evaluation/participation_cal_dryrun.py").read_text().lower()
    assert "calibration/" not in source
    assert "test/" not in source
    assert "read_csv(cal" not in source
