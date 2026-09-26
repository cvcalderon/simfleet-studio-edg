from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import yaml

from simfleet_edg.demand.time_schedule import (
    GLOBAL_TOKEN,
    build_time_b_encoder_manifest,
    build_time_backoff_model,
    fit_seed,
    multi_quantile_pinball,
    sample_time_a,
    transform_time_b_context,
    validate_source_temporal_targets,
    validate_temporal_row,
    weighted_pinball,
    weighted_reference_temporal_support,
)
from simfleet_edg.repro.f3_2f_fit_time_schedule import _fit_check_passed


def _frame() -> pd.DataFrame:
    rows = []
    for i in range(35):
        rows.append(
            {
                "origin_activity_analogue": "HOME",
                "destination_activity_analogue": "WORK",
                "trip_position_class": "FIRST",
                "primary_activity_status": "EMPLOYED",
                "source_weekday": "1",
                "target_departure_clock_minute": 480 + i % 3,
                "target_arrival_clock_minute": 500 + i % 3,
                "target_arrival_day_offset": 0,
                "target_duration_from_clock_min": 20,
                "fit_weight_W_GEW": 1.0,
            }
        )
    return pd.DataFrame(rows)


def test_fit_seed_deterministic() -> None:
    assert fit_seed(20260926, "TIME_A", "TA1") == fit_seed(20260926, "TIME_A", "TA1")
    assert fit_seed(20260926, "TIME_A", "TA1") != fit_seed(20260926, "TIME_A", "TA2")


def test_validate_temporal_row_valid() -> None:
    ok, row = validate_temporal_row(480, 30, previous_arrival_absolute_minute=450, trips_remaining_after_current=1)
    assert ok
    assert row["arrival_clock_minute"] == 510
    assert row["arrival_day_offset"] == 0


def test_validate_temporal_row_rejects_overlap() -> None:
    ok, _ = validate_temporal_row(480, 30, previous_arrival_absolute_minute=500, trips_remaining_after_current=0)
    assert not ok


def test_validate_temporal_row_rejects_nonfinal_overnight() -> None:
    ok, _ = validate_temporal_row(1430, 20, trips_remaining_after_current=1)
    assert not ok


def test_validate_temporal_row_allows_final_overnight() -> None:
    ok, row = validate_temporal_row(1430, 20, trips_remaining_after_current=0)
    assert ok
    assert row["arrival_day_offset"] == 1
    assert row["arrival_clock_minute"] == 10


def test_source_target_identity() -> None:
    df = pd.DataFrame(
        {
            "target_departure_clock_minute": [100, 1430],
            "target_arrival_clock_minute": [120, 10],
            "target_arrival_day_offset": [0, 1],
            "target_duration_from_clock_min": [20, 20],
        }
    )
    validate_source_temporal_targets(df)


def test_source_target_identity_rejects_mismatch() -> None:
    df = pd.DataFrame(
        {
            "target_departure_clock_minute": [100],
            "target_arrival_clock_minute": [121],
            "target_arrival_day_offset": [0],
            "target_duration_from_clock_min": [20],
        }
    )
    with pytest.raises(ValueError):
        validate_source_temporal_targets(df)


def test_reference_hour_pmf_normalized() -> None:
    model = weighted_reference_temporal_support(_frame())
    assert len(model["departure_hour_probabilities"]) == 24
    assert np.isclose(sum(model["departure_hour_probabilities"]), 1.0)
    assert np.isclose(sum(x["probability"] for x in model["joint_temporal_support"]), 1.0)


def test_backoff_low_n_rule_and_resolution() -> None:
    frame = _frame()
    hierarchy = [
        ["origin_activity_analogue", "destination_activity_analogue", "trip_position_class", "primary_activity_status", "source_weekday"],
        ["trip_position_class"],
        [GLOBAL_TOKEN],
    ]
    model, summary = build_time_backoff_model(frame, hierarchy, bandwidth_minutes=0, min_n=30, max_rejection_attempts=100)
    assert model["levels"][0]["cells"][0]["eligible_direct"] is True
    assert sum(row["train_rows_selected"] for row in summary) == len(frame)


def test_backoff_marks_low_n() -> None:
    frame = _frame().iloc[:10].copy()
    model, _ = build_time_backoff_model(frame, [["trip_position_class"], [GLOBAL_TOKEN]], bandwidth_minutes=0, min_n=30, max_rejection_attempts=100)
    assert model["levels"][0]["cells"][0]["low_n"] is True
    assert model["levels"][1]["cells"][0]["eligible_direct"] is True


def test_time_a_sampling_valid_bandwidth_zero() -> None:
    frame = _frame()
    hierarchy = [["trip_position_class"], [GLOBAL_TOKEN]]
    model, _ = build_time_backoff_model(frame, hierarchy, bandwidth_minutes=0, min_n=30, max_rejection_attempts=100)
    out = sample_time_a(model, {"trip_position_class": "FIRST"}, previous_arrival_absolute_minute=400, trips_remaining_after_current=1, seed=7)
    assert out["jitter_minute"] == 0
    assert out["departure_clock_minute"] in {480, 481, 482}


def test_time_a_sampling_jitter_is_bounded() -> None:
    frame = _frame()
    model, _ = build_time_backoff_model(frame, [[GLOBAL_TOKEN]], bandwidth_minutes=15, min_n=30, max_rejection_attempts=100)
    out = sample_time_a(model, {}, previous_arrival_absolute_minute=None, trips_remaining_after_current=0, seed=10)
    assert -15 <= out["jitter_minute"] <= 15


def test_time_a_sampling_rejects_and_raises_without_repair() -> None:
    frame = _frame()
    model, _ = build_time_backoff_model(frame, [[GLOBAL_TOKEN]], bandwidth_minutes=0, min_n=30, max_rejection_attempts=3)
    with pytest.raises(RuntimeError):
        sample_time_a(model, {}, previous_arrival_absolute_minute=1000, trips_remaining_after_current=0, seed=1)


def test_encoder_train_categories_and_unseen_mapping() -> None:
    train = pd.DataFrame({"cat": ["A", "B"], "num": [1.0, np.nan]})
    enc = build_time_b_encoder_manifest(train, ["cat"], ["num"])
    x, unseen = transform_time_b_context(pd.DataFrame({"cat": ["A", "C"], "num": [2.0, np.nan]}), enc)
    assert unseen["cat"] == 1
    assert x.shape[0] == 2
    assert np.isnan(x[1, -1])



def test_encoder_feature_names_lightgbm_safe() -> None:
    train = pd.DataFrame({"cat": ["A", "B"], "num": [1.0, 2.0]})
    enc = build_time_b_encoder_manifest(train, ["cat"], ["num"])
    forbidden = set('[]{}\":,')
    assert all(not forbidden.intersection(name) for name in enc["feature_names"])


def test_weighted_pinball_known_value() -> None:
    y = np.array([0.0, 2.0])
    pred = np.array([1.0, 1.0])
    w = np.array([1.0, 1.0])
    assert np.isclose(weighted_pinball(y, pred, 0.5, w), 0.5)


def test_multi_quantile_pinball_finite() -> None:
    y = np.array([1.0, 2.0])
    p = np.array([[0.5, 1.0, 1.5], [1.0, 2.0, 3.0]])
    value = multi_quantile_pinball(y, p, [0.25, 0.5, 0.75], np.ones(2))
    assert np.isfinite(value)


def test_config_frozen_candidate_grid() -> None:
    root = Path(__file__).resolve().parents[1]
    cfg = yaml.safe_load((root / "configs/f3/f3_2f_time_schedule_fit_v1.yaml").read_text())
    assert cfg["part_a"]["grids"] == {"TA1": {"bandwidth_min": 0}, "TA2": {"bandwidth_min": 15}, "TA3": {"bandwidth_min": 30}}
    assert set(cfg["part_b"]["grids"]) == {"TB1", "TB2", "TB3"}
    assert cfg["output_policy"]["expected_models"] == 7


def test_config_has_no_cal_or_test_input_path() -> None:
    root = Path(__file__).resolve().parents[1]
    text = (root / "configs/f3/f3_2f_time_schedule_fit_v1.yaml").read_text().lower()
    assert "calibration/time_trips" not in text
    assert "test/time_trips" not in text

def test_fit_check_expected_false_semantics() -> None:
    assert _fit_check_passed("test_partition_consumed", False)
    assert not _fit_check_passed("test_partition_consumed", True)
    assert _fit_check_passed("train_rows_exact", True)
    assert not _fit_check_passed("train_rows_exact", False)
