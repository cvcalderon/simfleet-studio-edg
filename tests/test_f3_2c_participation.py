from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

from simfleet_edg.demand.participation import (
    EncodedParticipationData,
    build_encoder_manifest,
    fit_logistic_l2,
    fit_reference,
    fit_seed,
    lightgbm_parameters,
    transform_context,
    weighted_logloss,
)

ROOT = Path(__file__).resolve().parents[1]
CFG = yaml.safe_load((ROOT / "configs/f3/f3_2c_participation_fit_v1.yaml").read_text())


def test_feature_set_is_exact_and_forbidden_fields_are_absent() -> None:
    features = CFG["feature_columns"]
    assert len(features) == 15
    text = "|".join(features).lower()
    assert all(str(token).lower() not in text for token in CFG["forbidden_feature_tokens"])


def test_frozen_participation_grids_are_exact() -> None:
    assert CFG["part_a"]["grids"] == {
        "PA1": {"lambda_l2": 0.1},
        "PA2": {"lambda_l2": 1.0},
        "PA3": {"lambda_l2": 10.0},
    }
    assert CFG["part_b"]["grids"]["PB1"] == {
        "max_depth": 2,
        "num_leaves": 4,
        "min_data_in_leaf": 30,
        "lambda_l2": 1.0,
    }


def test_fit_seed_is_sha256_uint32_big_endian() -> None:
    assert fit_seed(20260926, "PART_A", "PA1") == 2347447347
    assert fit_seed(20260926, "PART_B", "PB4") == 4164918344


def test_train_only_encoder_routes_unseen_without_refit() -> None:
    train = pd.DataFrame({"a": ["x", "y"], "b": [1, 2]})
    manifest = build_encoder_manifest(train, ["a", "b"])
    x_train, u_train = transform_context(train, manifest)
    x_new, u_new = transform_context(pd.DataFrame({"a": ["z"], "b": [3]}), manifest)
    assert x_train.shape[1] == x_new.shape[1]
    assert sum(u_train.values()) == 0
    assert u_new == {"a": 1, "b": 1}


def test_reference_is_weighted_empirical_bernoulli() -> None:
    data = EncodedParticipationData(
        x=np.zeros((3, 1)),
        y=np.array([0.0, 1.0, 1.0]),
        w=np.array([1.0, 1.0, 2.0]),
        feature_names=["x"],
        categories={"x": ["0"]},
        source_rows=3,
        weighted_observed_share=0.75,
    )
    model, p = fit_reference(data)
    assert model["probability_trip_day"] == 0.75
    assert np.allclose(p, 0.75)


def test_logistic_l2_fits_finite_probabilities() -> None:
    x = np.array([[1.0, 0.0], [0.0, 1.0], [1.0, 0.0], [0.0, 1.0]])
    y = np.array([0.0, 1.0, 0.0, 1.0])
    w = np.ones(4)
    data = EncodedParticipationData(x=x, y=y, w=w, feature_names=["a", "b"], categories={}, source_rows=4, weighted_observed_share=0.5)
    model, p = fit_logistic_l2(data, 0.1, 500, 1e-12, 1e-8)
    assert model["optimizer"]["success"] is True
    assert np.isfinite(p).all()
    assert np.all((p > 0) & (p < 1))
    assert weighted_logloss(y, p, w) < weighted_logloss(y, np.full(4, 0.5), w)


def test_lightgbm_parameters_match_frozen_grid() -> None:
    params = lightgbm_parameters(CFG["part_b"]["common"], CFG["part_b"]["grids"]["PB2"], 123)
    assert params["learning_rate"] == 0.05
    assert params["n_estimators"] == 200
    assert params["max_depth"] == 3
    assert params["num_leaves"] == 8
    assert params["min_child_samples"] == 30
    assert params["reg_lambda"] == 1.0
    assert params["random_state"] == 123
    assert params["deterministic"] is True
    assert params["n_jobs"] == 1


def test_config_forbids_cal_selection_and_test() -> None:
    assert CFG["calibration_policy"] == "DO_NOT_READ_DO_NOT_SCORE_DO_NOT_FIT"
    assert CFG["selection_policy"] == "NONE_IN_F3_2C"
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


def test_no_calibration_or_selection_fields_are_planned_as_metrics() -> None:
    text = json.dumps(CFG["output_policy"], sort_keys=True)
    assert '"cal_metrics_emitted": false' in text
    assert '"selection_decision_emitted": false' in text
