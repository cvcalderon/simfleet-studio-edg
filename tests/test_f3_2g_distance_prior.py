from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import yaml

from simfleet_edg.demand.distance_prior import (
    GLOBAL_TOKEN,
    build_distance_b_encoder_manifest,
    build_distance_backoff_model,
    fit_seed,
    inverse_ecdf_value,
    multi_quantile_pinball,
    repair_distance_quantiles,
    sample_distance_a,
    sample_distance_b,
    transform_distance_b_context,
    validate_distance_targets,
    weighted_reference_distance_support,
)
from simfleet_edg.repro.f3_2g_fit_distance_prior import _fit_check_passed


def _frame(n: int = 35) -> pd.DataFrame:
    rows = []
    for idx in range(n):
        rows.append(
            {
                "origin_activity_analogue": "HOME",
                "destination_activity_analogue": "WORK",
                "departure_period_analogue": "AM_PEAK",
                "primary_activity_status": "EMPLOYED_FULL_TIME",
                "age_infr_class": "08_40_59",
                "fit_weight_W_GEW": 1.0 + (idx % 3),
                "target_distance_prior_km": 1.0 + (idx % 5),
            }
        )
    return pd.DataFrame(rows)


def test_fit_seed_deterministic() -> None:
    assert fit_seed(20260926, "DIST_A", "DA1") == fit_seed(20260926, "DIST_A", "DA1")
    assert fit_seed(20260926, "DIST_B", "DB1") != fit_seed(20260926, "DIST_B", "DB2")


def test_validate_distance_targets_positive() -> None:
    validate_distance_targets(pd.DataFrame({"target_distance_prior_km": [0.01, 1.0, 50.0]}))


def test_validate_distance_targets_rejects_nonpositive() -> None:
    with pytest.raises(ValueError):
        validate_distance_targets(pd.DataFrame({"target_distance_prior_km": [0.0, 1.0]}))


def test_reference_ecdf_normalized_and_sorted() -> None:
    model = weighted_reference_distance_support(_frame())
    support = model["support"]
    assert np.isclose(sum(row["probability"] for row in support), 1.0)
    assert support[-1]["cumulative_probability"] == 1.0
    assert [row["distance_km"] for row in support] == sorted(row["distance_km"] for row in support)


def test_inverse_ecdf_endpoints() -> None:
    model = weighted_reference_distance_support(_frame())
    support = model["support"]
    assert inverse_ecdf_value(support, 0.0) == min(row["distance_km"] for row in support)
    assert inverse_ecdf_value(support, 1.0) == max(row["distance_km"] for row in support)


def test_backoff_low_n_rule_and_resolution() -> None:
    frame = _frame()
    hierarchy = [
        ["origin_activity_analogue", "destination_activity_analogue", "departure_period_analogue"],
        ["destination_activity_analogue"],
        [GLOBAL_TOKEN],
    ]
    model, summary = build_distance_backoff_model(frame, hierarchy, min_n=30)
    assert model["levels"][0]["cells"][0]["eligible_direct"] is True
    assert sum(row["train_rows_selected"] for row in summary) == len(frame)


def test_backoff_marks_low_n() -> None:
    model, _ = build_distance_backoff_model(_frame(10), [["destination_activity_analogue"], [GLOBAL_TOKEN]], min_n=30)
    assert model["levels"][0]["cells"][0]["low_n"] is True
    assert model["levels"][1]["cells"][0]["eligible_direct"] is True


def test_distance_a_sampling_returns_audit_trace() -> None:
    model, _ = build_distance_backoff_model(_frame(), [["destination_activity_analogue"], [GLOBAL_TOKEN]], min_n=30)
    out = sample_distance_a(model, {"destination_activity_analogue": "WORK"}, seed=7)
    assert out["selected_level"] == 1
    assert out["source_n"] == 35
    assert 1.0 <= out["distance_prior_km"] <= 5.0
    assert out["backoff_trace"][0]["eligible_direct"] is True


def test_encoder_train_categories_and_unseen_mapping() -> None:
    train = pd.DataFrame({"cat": ["A", "B"], "num": [1.0, np.nan]})
    enc = build_distance_b_encoder_manifest(train, ["cat"], ["num"])
    x, unseen = transform_distance_b_context(pd.DataFrame({"cat": ["A", "C"], "num": [2.0, np.nan]}), enc)
    assert unseen["cat"] == 1
    assert x.shape[0] == 2
    assert np.isnan(x[1, -1])


def test_encoder_feature_names_lightgbm_safe() -> None:
    enc = build_distance_b_encoder_manifest(pd.DataFrame({"cat": ["A", "B"], "num": [1.0, 2.0]}), ["cat"], ["num"])
    forbidden = set('[]{}\":,')
    assert all(not forbidden.intersection(name) for name in enc["feature_names"])


def test_repair_distance_quantiles_clamps_and_monotonises() -> None:
    raw = np.asarray([[5.0, 4.0, 20.0], [-1.0, 2.0, 3.0]])
    repaired = repair_distance_quantiles(raw, 0.5, 10.0)
    assert np.all(np.diff(repaired, axis=1) >= -1e-12)
    assert repaired.min() >= 0.5
    assert repaired.max() <= 10.0


def test_sample_distance_b_uses_global_endpoints() -> None:
    quantiles = [0.05, 0.5, 0.95]
    repaired = np.asarray([1.0, 5.0, 9.0])
    assert sample_distance_b(repaired, quantiles, uniform=0.0, target_min=0.1, target_max=20.0) == 0.1
    assert sample_distance_b(repaired, quantiles, uniform=1.0, target_min=0.1, target_max=20.0) == 20.0


def test_multi_quantile_pinball_finite() -> None:
    y = np.asarray([1.0, 2.0])
    pred = np.asarray([[0.5, 1.0, 1.5], [1.0, 2.0, 3.0]])
    assert np.isfinite(multi_quantile_pinball(y, pred, [0.25, 0.5, 0.75], np.ones(2)))


def test_config_frozen_candidate_grid() -> None:
    root = Path(__file__).resolve().parents[1]
    cfg = yaml.safe_load((root / "configs/f3/f3_2g_distance_prior_fit_v1.yaml").read_text())
    assert cfg["part_a"]["grids"] == {"DA1": {"inverse_ecdf_interpolation": "LINEAR_WEIGHTED"}}
    assert set(cfg["part_b"]["grids"]) == {"DB1", "DB2", "DB3"}
    assert cfg["output_policy"]["expected_models"] == 5


def test_config_distance_boundaries() -> None:
    root = Path(__file__).resolve().parents[1]
    cfg = yaml.safe_load((root / "configs/f3/f3_2g_distance_prior_fit_v1.yaml").read_text())
    assert cfg["primary_target"]["evidence"] == "RAW_WEGKM"
    assert cfg["sensitivity_target"]["consumed_for_primary_fit"] is False
    assert "km_routing" in cfg["forbidden_feature_tokens"]


def test_config_feature_mapping_exact() -> None:
    root = Path(__file__).resolve().parents[1]
    cfg = yaml.safe_load((root / "configs/f3/f3_2g_distance_prior_fit_v1.yaml").read_text())
    assert cfg["semantic_feature_mapping"]["generated_activity_chain"] == [
        "origin_activity_analogue",
        "destination_activity_analogue",
    ]
    assert cfg["semantic_feature_mapping"]["generated_trip_times"] == [
        "departure_clock_minute_analogue",
        "departure_period_analogue",
        "arrival_clock_minute_analogue",
        "duration_from_clock_min_analogue",
    ]


def test_config_has_no_cal_or_test_input_path() -> None:
    root = Path(__file__).resolve().parents[1]
    text = (root / "configs/f3/f3_2g_distance_prior_fit_v1.yaml").read_text().lower()
    assert "calibration/distance" not in text
    assert "test/distance" not in text


def test_fit_check_expected_false_semantics() -> None:
    for name in (
        "test_partition_consumed",
        "calibration_partition_consumed",
        "candidate_selection_performed",
        "sensitivity_target_consumed_for_fit",
        "km_routing_consumed",
    ):
        assert _fit_check_passed(name, False)
        assert not _fit_check_passed(name, True)
    assert _fit_check_passed("train_rows_exact", True)
    assert not _fit_check_passed("train_rows_exact", False)
