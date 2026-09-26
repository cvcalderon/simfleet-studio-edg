from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import yaml

from simfleet_edg.demand.activity_chain import (
    build_chain_backoff_model,
    encode_chain_b_train,
    fit_multinomial_l2,
    fit_reference_transition_model,
    fit_seed,
    generate_activity_chain,
    target_activity_classes,
    training_metrics,
    transform_chain_b_context,
    validate_chain_structure,
)

ROOT = Path(__file__).resolve().parents[1]
CFG = yaml.safe_load((ROOT / "configs/f3/f3_2e_activity_chain_fit_v1.yaml").read_text())


def _toy_chain() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    context = pd.DataFrame(
        {
            "row_id": ["a", "b", "c", "d"],
            "age_infr_class": ["A", "A", "B", "B"],
            "sex": ["F", "M", "F", "M"],
            "primary_activity_status": ["WORKER", "WORKER", "STUDENT", "STUDENT"],
            "household_size_class": ["1", "2", "2", "3"],
            "source_weekday": [1, 1, 2, 2],
        }
    )
    days = pd.DataFrame(
        {
            "context_row_id": ["a", "b", "c", "d"],
            "source_household_id": [1, 2, 3, 4],
            "source_person_id": [11, 21, 31, 41],
            "source_trip_count_analogue": [2, 2, 2, 2],
            "first_origin_activity": ["HOME"] * 4,
            "final_destination_activity": ["HOME", "WORK", "HOME", "EDUCATION"],
            "target_return_home": [True, False, True, False],
            "day_weight_P_GEW": [1.0, 2.0, 1.0, 1.0],
        }
    )
    rows = []
    destinations = [
        ("WORK", "HOME"),
        ("SHOPPING", "WORK"),
        ("EDUCATION", "HOME"),
        ("LEISURE", "EDUCATION"),
    ]
    for context_id, (first, second), person in zip(
        ["a", "b", "c", "d"], destinations, [11, 21, 31, 41], strict=True
    ):
        rows.extend(
            [
                {
                    "context_row_id": context_id,
                    "source_household_id": person // 10,
                    "source_person_id": person,
                    "source_trip_id": 1,
                    "trip_sequence_index": 1,
                    "source_trip_count_analogue": 2,
                    "prefix_second_last_activity": "__START__",
                    "prefix_last_activity": "HOME",
                    "remaining_trips": 1,
                    "canonical_trip_purpose": first,
                    "target_destination_activity": first,
                    "fit_weight_W_GEW": 1.0,
                },
                {
                    "context_row_id": context_id,
                    "source_household_id": person // 10,
                    "source_person_id": person,
                    "source_trip_id": 2,
                    "trip_sequence_index": 2,
                    "source_trip_count_analogue": 2,
                    "prefix_second_last_activity": "HOME",
                    "prefix_last_activity": first,
                    "remaining_trips": 0,
                    "canonical_trip_purpose": second,
                    "target_destination_activity": second,
                    "fit_weight_W_GEW": 1.0,
                },
            ]
        )
    transitions = pd.DataFrame(rows)
    merged = transitions.merge(
        context,
        left_on="context_row_id",
        right_on="row_id",
        how="left",
        validate="many_to_one",
    )
    return days, transitions, merged


def test_feature_set_is_literal_freeze() -> None:
    assert CFG["categorical_feature_columns"] == [
        "age_infr_class",
        "sex",
        "primary_activity_status",
        "household_size_class",
        "source_weekday",
        "prefix_second_last_activity",
        "prefix_last_activity",
    ]
    assert CFG["numeric_feature_columns"] == ["source_trip_count_analogue", "remaining_trips"]
    assert "source_season" not in CFG["categorical_feature_columns"]


def test_frozen_chain_grids_are_exact() -> None:
    assert CFG["part_a"]["grids"] == {
        "CHA1": {"dirichlet_alpha": 0.1},
        "CHA2": {"dirichlet_alpha": 1.0},
    }
    assert CFG["part_b"]["grids"] == {
        "CHB1": {"lambda_l2": 0.1},
        "CHB2": {"lambda_l2": 1.0},
        "CHB3": {"lambda_l2": 10.0},
    }


def test_chain_backoff_hierarchy_is_literal_freeze() -> None:
    assert CFG["part_a"]["hierarchy"] == [
        [
            "prefix_second_last_activity",
            "prefix_last_activity",
            "remaining_trips",
            "primary_activity_status",
            "source_weekday",
        ],
        ["prefix_last_activity", "remaining_trips", "primary_activity_status", "source_weekday"],
        ["prefix_last_activity", "remaining_trips", "primary_activity_status"],
        ["prefix_last_activity", "remaining_trips"],
        ["prefix_last_activity"],
        ["remaining_trips"],
        ["GLOBAL"],
    ]
    assert CFG["part_a"]["direct_support_min_n"] == 30


def test_fit_seed_is_frozen_sha256_rule() -> None:
    assert fit_seed(20260926, "CHAIN_A", "CHA1") == fit_seed(20260926, "CHAIN_A", "CHA1")
    assert fit_seed(20260926, "CHAIN_A", "CHA1") != fit_seed(20260926, "CHAIN_A", "CHA2")
    assert fit_seed(20260926, "CHAIN_B", "CHB1") != fit_seed(20260926, "CHAIN_B", "CHB2")


def test_chain_structure_requires_exact_k_and_prefix_continuity() -> None:
    days, transitions, _ = _toy_chain()
    validate_chain_structure(days, transitions)
    broken = transitions.copy()
    broken.loc[1, "prefix_last_activity"] = "BROKEN"
    try:
        validate_chain_structure(days, broken)
    except ValueError:
        pass
    else:
        raise AssertionError("Broken prefix continuity must fail")


def test_target_support_excludes_reserved_tokens() -> None:
    _, _, merged = _toy_chain()
    classes = target_activity_classes(merged)
    assert "__START__" not in classes
    assert "__UNSEEN__" not in classes
    assert "HOME" in classes


def test_reference_is_weighted_first_order_transition_matrix() -> None:
    _, _, merged = _toy_chain()
    classes = target_activity_classes(merged)
    model, probs = fit_reference_transition_model(merged, classes)
    assert model["model_type"] == "WEIGHTED_FIRST_ORDER_TRANSITION_MATRIX_V1"
    assert model["conditioning"] == ["prefix_last_activity"]
    assert model["return_home_forced"] is False
    assert np.allclose(probs.sum(axis=1), 1.0)


def test_chain_a_backoff_uses_raw_n_and_dirichlet_smoothing() -> None:
    _, _, merged = _toy_chain()
    classes = target_activity_classes(merged)
    model, probs, summary = build_chain_backoff_model(
        merged,
        CFG["part_a"]["hierarchy"],
        classes,
        min_n=30,
        alpha=0.1,
    )
    assert model["support_count_basis"] == "RAW_STRICT_TRAIN_ROWS_BEFORE_WEIGHTING"
    assert model["dirichlet_alpha"] == 0.1
    assert model["return_home_forced"] is False
    assert summary.loc[summary["level"] == 7, "train_rows_selected"].item() == len(merged)
    assert np.all(probs > 0)
    assert np.allclose(probs.sum(axis=1), 1.0)


def test_chain_b_encoder_is_train_only_and_routes_unseen() -> None:
    _, _, merged = _toy_chain()
    classes = target_activity_classes(merged)
    data = encode_chain_b_train(
        merged,
        CFG["categorical_feature_columns"],
        CFG["numeric_feature_columns"],
        classes,
    )
    assert data.encoder_manifest["fit_partition"] == "TRAIN"
    assert data.encoder_manifest["rare_pooling"] == "NONE"
    new = merged.head(1).copy()
    new["age_infr_class"] = "NEVER_SEEN"
    x, unseen = transform_chain_b_context(new, data.encoder_manifest)
    assert x.shape[1] == data.x.shape[1]
    assert unseen["age_infr_class"] == 1


def test_chain_b_multinomial_fit_returns_valid_probabilities() -> None:
    _, _, merged = _toy_chain()
    classes = target_activity_classes(merged)
    data = encode_chain_b_train(
        merged,
        CFG["categorical_feature_columns"],
        CFG["numeric_feature_columns"],
        classes,
    )
    model, probs = fit_multinomial_l2(
        data,
        lambda_l2=1.0,
        maxiter=1000,
        ftol=1e-12,
        gtol=1e-8,
        coefficient_bounds=(-20.0, 20.0),
        reject_if_boundary_hit=True,
    )
    assert model["optimizer"]["success"] is True
    assert model["optimizer"]["boundary_hit"] is False
    assert np.all(np.isfinite(probs))
    assert np.allclose(probs.sum(axis=1), 1.0)


def test_training_metrics_are_finite_and_include_final_home() -> None:
    _, _, merged = _toy_chain()
    classes = target_activity_classes(merged)
    _, probs = fit_reference_transition_model(merged, classes)
    metrics = training_metrics(merged, classes, probs)
    assert np.isfinite(list(metrics.values())).all()
    assert "weighted_next_activity_log_loss" in metrics
    assert "weighted_observed_final_home_share" in metrics


def test_generated_chain_has_exactly_k_transitions_and_does_not_force_home() -> None:
    def callback(activities: list[str], remaining: int, index: int):
        del activities, remaining, index
        return ["WORK", "LEISURE"], np.asarray([0.0, 1.0])

    chain = generate_activity_chain(3, "HOME", callback, np.random.default_rng(123))
    assert len(chain) == 4
    assert chain[-1] == "LEISURE"
    assert chain[-1] != "HOME"


def test_authoritative_materialized_row_counts_are_frozen() -> None:
    assert CFG["expected_context_rows"] == 2200
    assert CFG["expected_train_day_rows"] == 1422
    assert CFG["expected_train_transition_rows"] == 4872


def test_purpose_return_home_and_weights_are_forbidden_features() -> None:
    feature_text = "|".join(
        CFG["categorical_feature_columns"] + CFG["numeric_feature_columns"]
    ).lower()
    for token in ["canonical_trip_purpose", "target_return_home", "fit_weight_w_gew"]:
        assert token not in feature_text


def test_config_forbids_cal_selection_and_test() -> None:
    assert CFG["calibration_policy"] == "DO_NOT_READ_DO_NOT_SCORE_DO_NOT_FIT"
    assert CFG["selection_policy"] == "NONE_IN_F3_2E"
    assert CFG["test_partition"] == "SEALED"
    assert CFG["output_policy"]["cal_metrics_emitted"] is False
    assert CFG["output_policy"]["selection_decision_emitted"] is False
    assert CFG["output_policy"]["expected_models"] == 6


def test_split_and_environment_are_frozen() -> None:
    assert CFG["split_manifest_sha256"] == (
        "5d0d4f2a41bc93b131de96d85192d8ff7002878e28e87515a0f88cedf1cebde8"
    )
    assert CFG["environment_witness"]["required_versions"] == {
        "numpy": "2.5.3",
        "pandas": "2.3.3",
        "scipy": "1.18.1",
        "scikit-learn": "1.9.1",
        "statsmodels": "0.15.0",
        "lightgbm": "4.7.0",
    }
