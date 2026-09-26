from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

from simfleet_edg.demand.trip_count import (
    build_count_a_encoder_manifest,
    build_count_backoff_model,
    canonical_count_keys,
    fit_nb2_l2,
    fit_reference,
    fit_seed,
    nb2_truncated_pmf_matrix,
    transform_count_context,
    weighted_discrete_crps,
)

ROOT = Path(__file__).resolve().parents[1]
CFG = yaml.safe_load((ROOT / "configs/f3/f3_2d_trip_count_fit_v1.yaml").read_text())


def _toy_data():
    from simfleet_edg.demand.trip_count import EncodedCountData

    x = np.array(
        [
            [0.0, 0.0],
            [1.0, 0.0],
            [0.0, 1.0],
            [1.0, 1.0],
            [0.0, 0.0],
            [1.0, 0.0],
            [0.0, 1.0],
            [1.0, 1.0],
        ],
        dtype=float,
    )
    k = np.array([1, 2, 2, 4, 1, 3, 2, 5], dtype=np.int64)
    y = k.astype(float) - 1.0
    w = np.ones(len(k), dtype=float)
    merged = pd.DataFrame(
        {
            "target_trip_count": k,
            "fit_weight_P_GEW_target": w,
            "age_infr_class": ["A", "A", "B", "B", "A", "A", "B", "B"],
            "sex": ["M", "F", "M", "F", "M", "F", "M", "F"],
            "primary_activity_status": ["X"] * 8,
            "household_size_class": ["1", "1", "2", "2", "1", "1", "2", "2"],
            "source_weekday": ["1", "1", "1", "1", "2", "2", "2", "2"],
            "source_season": ["S"] * 8,
        }
    )
    return EncodedCountData(
        x=x,
        y=y,
        k=k,
        w=w,
        source_rows=len(k),
        feature_names=["x1", "x2"],
        categories={},
        reference_categories={},
        merged=merged,
        k_min=1,
        k_max=5,
    )


def test_feature_set_is_exact_and_forbidden_fields_are_absent() -> None:
    assert CFG["feature_columns"] == [
        "age_infr_class",
        "sex",
        "primary_activity_status",
        "household_size_class",
        "source_weekday",
        "source_season",
    ]
    text = "|".join(CFG["feature_columns"]).lower()
    assert all(str(token).lower() not in text for token in CFG["forbidden_feature_tokens"])


def test_frozen_trip_count_grids_are_exact() -> None:
    assert CFG["part_a"]["grids"] == {
        "CA1": {"lambda_l2": 0.0},
        "CA2": {"lambda_l2": 0.1},
        "CA3": {"lambda_l2": 1.0},
    }
    assert CFG["part_b"]["grid_id"] == "CB1"
    assert CFG["part_b"]["smoothing"] == "NONE"


def test_count_backoff_hierarchy_is_literal_freeze() -> None:
    assert CFG["part_b"]["hierarchy"] == [
        ["age_infr_class", "sex", "primary_activity_status", "household_size_class", "source_weekday"],
        ["age_infr_class", "sex", "primary_activity_status", "household_size_class"],
        ["age_infr_class", "sex", "primary_activity_status"],
        ["age_infr_class", "primary_activity_status"],
        ["primary_activity_status"],
        ["age_infr_class"],
        ["GLOBAL"],
    ]
    assert all("source_season" not in level for level in CFG["part_b"]["hierarchy"])


def test_positive_support_and_tail_policy_are_exact() -> None:
    assert CFG["k_min"] == 1
    assert CFG["k_max_train"] == 50
    assert CFG["part_a"]["tail_policy"] == "TRUNCATE_AND_RENORMALIZE_NB2_TO_K_1_THROUGH_K_MAX_TRAIN"
    assert CFG["part_a"]["posthoc_clip"] is False


def test_fit_seed_is_sha256_uint32_big_endian() -> None:
    assert fit_seed(20260926, "COUNT_A", "CA1") == 4163565600
    assert fit_seed(20260926, "COUNT_A", "CA2") == 91420992
    assert fit_seed(20260926, "COUNT_A", "CA3") == 1040180436
    assert fit_seed(20260926, "COUNT_B", "CB1") == 546212382


def test_reference_encoder_is_identifiable_and_routes_unseen() -> None:
    train = pd.DataFrame({"a": ["x", "y", "x"], "b": [1, 2, 1]})
    manifest = build_count_a_encoder_manifest(train, ["a", "b"])
    assert manifest["reference_categories"] == {"a": "x", "b": "1"}
    assert "a==x" not in manifest["feature_names"]
    assert "b==1" not in manifest["feature_names"]
    x_train, unseen_train = transform_count_context(train, manifest)
    x_new, unseen_new = transform_count_context(pd.DataFrame({"a": ["z"], "b": [3]}), manifest)
    assert x_train.shape[1] == x_new.shape[1]
    assert sum(unseen_train.values()) == 0
    assert unseen_new == {"a": 1, "b": 1}


def test_reference_is_weighted_empirical_positive_count_pmf() -> None:
    data = _toy_data()
    model, pmf = fit_reference(data)
    assert model["support_k"] == [1, 2, 3, 4, 5]
    assert np.isclose(pmf.sum(), 1.0)
    assert np.isclose(pmf[0], 2 / 8)
    assert np.isclose(pmf[1], 3 / 8)


def test_discrete_crps_is_zero_for_perfect_point_mass() -> None:
    observed = np.array([1, 3], dtype=np.int64)
    pmf = np.array([[1.0, 0.0, 0.0], [0.0, 0.0, 1.0]])
    w = np.ones(2)
    assert weighted_discrete_crps(observed, pmf, w, 1) == 0.0


def test_nb2_truncated_pmf_is_renormalized_not_clipped() -> None:
    pmf = nb2_truncated_pmf_matrix(np.array([2.0, 5.0]), alpha=0.7, k_min=1, k_max=5)
    assert pmf.shape == (2, 5)
    assert np.allclose(pmf.sum(axis=1), 1.0)
    assert np.all(pmf > 0)


def test_nb2_l2_fit_is_finite_positive_dispersion_and_not_on_boundary() -> None:
    from simfleet_edg.demand.trip_count import EncodedCountData

    k = np.array([1, 1, 1, 1, 1, 2, 2, 10, 15, 20], dtype=np.int64)
    y = k.astype(float) - 1.0
    w = np.ones(len(k), dtype=float)
    merged = pd.DataFrame(
        {
            "target_trip_count": k,
            "fit_weight_P_GEW_target": w,
            "age_infr_class": ["A"] * len(k),
            "sex": ["M"] * len(k),
            "primary_activity_status": ["X"] * len(k),
            "household_size_class": ["1"] * len(k),
            "source_weekday": ["1"] * len(k),
            "source_season": ["S"] * len(k),
        }
    )
    data = EncodedCountData(
        x=np.zeros((len(k), 1)),
        y=y,
        k=k,
        w=w,
        source_rows=len(k),
        feature_names=["x1"],
        categories={},
        reference_categories={},
        merged=merged,
        k_min=1,
        k_max=20,
    )
    model, pmfs = fit_nb2_l2(
        data,
        lambda_l2=0.1,
        maxiter=1000,
        ftol=1e-12,
        gtol=1e-8,
        coefficient_bounds=(-20.0, 20.0),
        log_alpha_bounds=(-12.0, 8.0),
        reject_if_boundary_hit=True,
    )
    assert model["optimizer"]["success"] is True
    assert model["optimizer"]["boundary_hit"] is False
    assert model["alpha"] > 0
    assert np.all(np.isfinite(pmfs))
    assert np.allclose(pmfs.sum(axis=1), 1.0)


def test_backoff_uses_raw_n_threshold_and_reaches_global() -> None:
    data = _toy_data()
    hierarchy = [["age_infr_class", "sex"], ["age_infr_class"], ["GLOBAL"]]
    model, pmfs, summary = build_count_backoff_model(
        data.merged,
        hierarchy,
        "fit_weight_P_GEW_target",
        "target_trip_count",
        1,
        5,
        direct_support_min_n=30,
    )
    assert model["direct_support_min_n"] == 30
    assert model["smoothing"] == "NONE"
    assert summary.loc[summary["level"] == 3, "train_rows_selected"].item() == len(data.merged)
    assert np.allclose(pmfs.sum(axis=1), 1.0)


def test_canonical_count_keys_are_lexically_sorted_and_numeric_ordered() -> None:
    keys = canonical_count_keys(1, 50)
    assert keys == sorted(keys)
    assert keys[0] == "K:000001"
    assert keys[-1] == "K:000050"


def test_config_forbids_cal_selection_and_test() -> None:
    assert CFG["calibration_policy"] == "DO_NOT_READ_DO_NOT_SCORE_DO_NOT_FIT"
    assert CFG["selection_policy"] == "NONE_IN_F3_2D"
    assert CFG["test_partition"] == "SEALED"
    assert CFG["output_policy"]["cal_metrics_emitted"] is False
    assert CFG["output_policy"]["selection_decision_emitted"] is False


def test_split_manifest_hash_is_frozen() -> None:
    assert CFG["split_manifest_sha256"] == "5d0d4f2a41bc93b131de96d85192d8ff7002878e28e87515a0f88cedf1cebde8"


def test_required_environment_versions_are_frozen() -> None:
    assert CFG["environment_witness"]["required_versions"] == {
        "numpy": "2.5.3",
        "pandas": "2.3.3",
        "scipy": "1.18.1",
        "scikit-learn": "1.9.1",
        "statsmodels": "0.15.0",
        "lightgbm": "4.7.0",
    }


def test_no_calibration_or_selection_fields_are_planned_as_outputs() -> None:
    text = json.dumps(CFG["output_policy"], sort_keys=True)
    assert '"cal_metrics_emitted": false' in text
    assert '"selection_decision_emitted": false' in text
    assert CFG["output_policy"]["expected_models"] == 5
