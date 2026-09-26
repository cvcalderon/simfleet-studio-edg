from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from scipy.optimize import minimize
from scipy.special import logsumexp

RESERVED_UNSEEN = "__UNSEEN__"
RESERVED_MISSING = "__MISSING_CONTEXT__"
GLOBAL_TOKEN = "GLOBAL"
START_TOKEN = "__START__"


@dataclass(frozen=True)
class EncodedChainData:
    x: np.ndarray
    y: np.ndarray
    w: np.ndarray
    source_rows: int
    feature_names: list[str]
    target_classes: list[str]
    merged: pd.DataFrame
    encoder_manifest: dict[str, Any]


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def canonical_json_bytes(obj: Any) -> bytes:
    return (json.dumps(obj, sort_keys=True, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def fit_seed(master_seed: int, candidate_id: str, grid_id: str) -> int:
    payload = f'F3_1C|{master_seed}|{candidate_id}|{grid_id}|FIT'.encode()
    return int.from_bytes(hashlib.sha256(payload).digest()[:4], byteorder="big", signed=False)


def _as_category(value: Any) -> str:
    if pd.isna(value):
        return RESERVED_MISSING
    if isinstance(value, (np.integer, int)):
        return str(int(value))
    if isinstance(value, (np.floating, float)) and float(value).is_integer():
        return str(int(value))
    return str(value)


def _observed_categories(series: pd.Series) -> list[str]:
    return sorted({_as_category(value) for value in series.tolist() if not pd.isna(value)})


def assert_pmf(pmf: np.ndarray, atol: float = 1e-12) -> None:
    array = np.asarray(pmf, dtype=float)
    if array.ndim not in (1, 2):
        raise ValueError("PMF must be one- or two-dimensional")
    if not np.isfinite(array).all() or np.any(array < -atol):
        raise ValueError("PMF contains invalid probabilities")
    sums = array.sum(axis=-1)
    if not np.allclose(sums, 1.0, rtol=0.0, atol=atol):
        raise ValueError("PMF rows do not sum to one")


def weighted_categorical_pmf(
    values: pd.Series | np.ndarray,
    weights: pd.Series | np.ndarray,
    classes: list[str],
    alpha: float = 0.0,
) -> np.ndarray:
    mass = np.full(len(classes), float(alpha), dtype=np.float64)
    index = {value: i for i, value in enumerate(classes)}
    for value, weight in zip(values, weights, strict=True):
        key = str(value)
        if key not in index:
            raise ValueError(f"Target class outside frozen support: {key}")
        w = float(weight)
        if not math.isfinite(w) or w <= 0:
            raise ValueError("All fitting weights must be finite and positive")
        mass[index[key]] += w
    total = float(mass.sum())
    if not math.isfinite(total) or total <= 0:
        raise ValueError("Categorical PMF has no finite positive mass")
    pmf = mass / total
    assert_pmf(pmf)
    return pmf


def weighted_log_loss(
    y: np.ndarray,
    probs: np.ndarray,
    weights: np.ndarray,
    eps: float = 1e-15,
) -> float:
    p = np.asarray(probs, dtype=float)
    assert_pmf(p)
    yi = np.asarray(y, dtype=np.int64)
    w = np.asarray(weights, dtype=float)
    if p.shape[0] != len(yi) or len(yi) != len(w):
        raise ValueError("Prediction, target and weight row counts differ")
    chosen = np.clip(p[np.arange(len(yi)), yi], eps, 1.0)
    return float(np.average(-np.log(chosen), weights=w))


def finite_metrics(metrics: dict[str, float]) -> bool:
    return all(math.isfinite(float(value)) for value in metrics.values())


def validate_chain_structure(days: pd.DataFrame, transitions: pd.DataFrame) -> None:
    if days["context_row_id"].duplicated().any():
        raise ValueError("chain_days must have one row per context_row_id")
    if transitions[["context_row_id", "source_trip_id"]].duplicated().any():
        raise ValueError("chain_transitions contains duplicate trip keys")

    day_map = days.set_index("context_row_id")
    grouped = transitions.sort_values(["context_row_id", "trip_sequence_index"]).groupby(
        "context_row_id", sort=False
    )
    if set(grouped.groups) != set(day_map.index):
        raise ValueError("chain_days and chain_transitions context ids differ")

    for context_id, group in grouped:
        group = group.sort_values("trip_sequence_index")
        day = day_map.loc[context_id]
        k = int(day["source_trip_count_analogue"])
        if len(group) != k:
            raise ValueError(f"{context_id}: expected K={k} transitions, got {len(group)}")
        expected_idx = np.arange(1, k + 1, dtype=int)
        if not np.array_equal(group["trip_sequence_index"].astype(int).to_numpy(), expected_idx):
            raise ValueError(f"{context_id}: non-contiguous transition indices")
        expected_remaining = k - expected_idx
        if not np.array_equal(group["remaining_trips"].astype(int).to_numpy(), expected_remaining):
            raise ValueError(f"{context_id}: remaining_trips mismatch")
        rows = group.to_dict("records")
        if str(rows[0]["prefix_second_last_activity"]) != START_TOKEN:
            raise ValueError(f"{context_id}: first second-last prefix must be START")
        if str(rows[0]["prefix_last_activity"]) != str(day["first_origin_activity"]):
            raise ValueError(f"{context_id}: first origin mismatch")
        for previous, current in zip(rows[:-1], rows[1:], strict=True):
            if str(current["prefix_last_activity"]) != str(previous["target_destination_activity"]):
                raise ValueError(f"{context_id}: prefix continuity mismatch")
            if str(current["prefix_second_last_activity"]) != str(previous["prefix_last_activity"]):
                raise ValueError(f"{context_id}: order-2 prefix continuity mismatch")
        if str(rows[-1]["target_destination_activity"]) != str(day["final_destination_activity"]):
            raise ValueError(f"{context_id}: final destination mismatch")


def load_train_chain_tables(
    materialized_root: Path,
    expected_day_rows: int,
    expected_transition_rows: int,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    context = pd.read_csv(materialized_root / "TRAIN" / "person_day_context.csv")
    days = pd.read_csv(materialized_root / "TRAIN" / "chain_days.csv")
    transitions = pd.read_csv(materialized_root / "TRAIN" / "chain_transitions.csv")
    if len(days) != expected_day_rows:
        raise ValueError(f"Expected {expected_day_rows} TRAIN chain days, got {len(days)}")
    if len(transitions) != expected_transition_rows:
        raise ValueError(
            f"Expected {expected_transition_rows} TRAIN chain transitions, got {len(transitions)}"
        )
    validate_chain_structure(days, transitions)
    if int(days["source_trip_count_analogue"].sum()) != len(transitions):
        raise ValueError("Sum of day K does not equal transition rows")

    merged = transitions.merge(
        context,
        left_on="context_row_id",
        right_on="row_id",
        how="left",
        validate="many_to_one",
        suffixes=("_transition", "_context"),
    )
    if merged["row_id"].isna().any():
        raise ValueError("Every chain transition must resolve to person_day_context")
    weights = merged["fit_weight_W_GEW"].astype(float).to_numpy()
    if not np.isfinite(weights).all() or np.any(weights <= 0):
        raise ValueError("All W_GEW transition weights must be finite and positive")
    day_weights = days["day_weight_P_GEW"].astype(float).to_numpy()
    if not np.isfinite(day_weights).all() or np.any(day_weights <= 0):
        raise ValueError("All P_GEW day weights must be finite and positive")
    return context, days, merged


def target_activity_classes(merged: pd.DataFrame) -> list[str]:
    classes = sorted({str(value) for value in merged["target_destination_activity"].tolist()})
    if not classes:
        raise ValueError("No activity target classes")
    forbidden = {START_TOKEN, RESERVED_MISSING, RESERVED_UNSEEN}
    if forbidden.intersection(classes):
        raise ValueError("Reserved tokens cannot be generated target activities")
    return classes


def build_chain_b_encoder_manifest(
    train: pd.DataFrame,
    categorical_columns: list[str],
    numeric_columns: list[str],
    classes: list[str],
) -> dict[str, Any]:
    categories: dict[str, list[str]] = {}
    references: dict[str, str] = {}
    feature_names: list[str] = []
    for column in categorical_columns:
        observed = _observed_categories(train[column])
        if not observed:
            observed = [RESERVED_MISSING]
        reference = observed[0]
        full = list(observed)
        for token in (RESERVED_MISSING, RESERVED_UNSEEN):
            if token not in full:
                full.append(token)
        categories[column] = full
        references[column] = reference
        feature_names.extend(f"{column}=={value}" for value in full if value != reference)

    numeric_scalers: dict[str, dict[str, float]] = {}
    for column in numeric_columns:
        values = train[column].astype(float).to_numpy()
        if not np.isfinite(values).all():
            raise ValueError(f"Numeric chain feature contains non-finite values: {column}")
        mean = float(np.mean(values))
        scale = float(np.std(values, ddof=0))
        if not math.isfinite(scale) or scale <= 1e-12:
            scale = 1.0
        numeric_scalers[column] = {"mean": mean, "scale": scale}
        feature_names.append(f"z:{column}")

    return {
        "encoder": "DETERMINISTIC_REFERENCE_ONE_HOT_PLUS_ZSCORE_V1",
        "fit_partition": "TRAIN",
        "categorical_columns": categorical_columns,
        "numeric_columns": numeric_columns,
        "categories": categories,
        "reference_categories": references,
        "numeric_scalers": numeric_scalers,
        "feature_names": feature_names,
        "target_classes": classes,
        "target_reference_class": classes[0],
        "category_order": "CANONICAL_LEXICAL_OBSERVED_THEN_RESERVED_TOKENS",
        "reference_policy": "FIRST_OBSERVED_CANONICAL_CATEGORY_PER_FIELD",
        "unknown_token": RESERVED_UNSEEN,
        "missing_token": RESERVED_MISSING,
        "rare_pooling": "NONE",
    }


def transform_chain_b_context(
    context: pd.DataFrame,
    encoder: dict[str, Any],
) -> tuple[np.ndarray, dict[str, int]]:
    blocks: list[np.ndarray] = []
    unseen_counts: dict[str, int] = {}
    for column in encoder["categorical_columns"]:
        full = list(encoder["categories"][column])
        reference = str(encoder["reference_categories"][column])
        encoded = [value for value in full if value != reference]
        encoded_index = {value: index for index, value in enumerate(encoded)}
        full_set = set(full)
        values = [_as_category(value) for value in context[column].tolist()]
        mapped = [value if value in full_set else RESERVED_UNSEEN for value in values]
        unseen_counts[column] = sum(value == RESERVED_UNSEEN for value in mapped)
        block = np.zeros((len(context), len(encoded)), dtype=np.float64)
        for row_index, value in enumerate(mapped):
            if value != reference:
                block[row_index, encoded_index[value]] = 1.0
        blocks.append(block)

    for column in encoder["numeric_columns"]:
        scaler = encoder["numeric_scalers"][column]
        values = context[column].astype(float).to_numpy()
        z = (values - float(scaler["mean"])) / float(scaler["scale"])
        blocks.append(z[:, np.newaxis].astype(np.float64))

    if not blocks:
        return np.zeros((len(context), 0), dtype=np.float64), unseen_counts
    return np.concatenate(blocks, axis=1), unseen_counts


def encode_chain_b_train(
    merged: pd.DataFrame,
    categorical_columns: list[str],
    numeric_columns: list[str],
    classes: list[str],
) -> EncodedChainData:
    encoder = build_chain_b_encoder_manifest(
        merged,
        categorical_columns,
        numeric_columns,
        classes,
    )
    x, unseen = transform_chain_b_context(merged, encoder)
    if any(unseen.values()):
        raise ValueError("TRAIN chain encoder produced unseen categories from TRAIN")
    class_index = {value: i for i, value in enumerate(classes)}
    y = np.asarray([class_index[str(value)] for value in merged["target_destination_activity"]])
    w = merged["fit_weight_W_GEW"].astype(float).to_numpy()
    return EncodedChainData(
        x=x,
        y=y,
        w=w,
        source_rows=len(merged),
        feature_names=list(encoder["feature_names"]),
        target_classes=classes,
        merged=merged,
        encoder_manifest=encoder,
    )


def feature_matrix_sha256(data: EncodedChainData) -> str:
    h = hashlib.sha256()
    h.update(str(data.x.shape).encode())
    h.update(np.ascontiguousarray(data.x, dtype=np.float64).tobytes())
    h.update(np.ascontiguousarray(data.y, dtype=np.int64).tobytes())
    h.update(np.ascontiguousarray(data.w, dtype=np.float64).tobytes())
    h.update("\n".join(data.feature_names).encode())
    h.update("\n".join(data.target_classes).encode())
    return h.hexdigest()


def _cell_key(row: pd.Series | dict[str, Any], dimensions: list[str]) -> tuple[str, ...]:
    if dimensions == [GLOBAL_TOKEN]:
        return (GLOBAL_TOKEN,)
    return tuple(_as_category(row[dimension]) for dimension in dimensions)


def _serialize_key(dimensions: list[str], key: tuple[str, ...]) -> list[dict[str, str]]:
    return [{"dimension": dim, "value": value} for dim, value in zip(dimensions, key, strict=True)]


def fit_reference_transition_model(
    merged: pd.DataFrame,
    classes: list[str],
) -> tuple[dict[str, Any], np.ndarray]:
    weight_col = "fit_weight_W_GEW"
    target_col = "target_destination_activity"
    global_pmf = weighted_categorical_pmf(merged[target_col], merged[weight_col], classes)
    cells: list[dict[str, Any]] = []
    lookup: dict[str, np.ndarray] = {}
    for previous, group in merged.groupby("prefix_last_activity", sort=True, dropna=False):
        key = _as_category(previous)
        pmf = weighted_categorical_pmf(group[target_col], group[weight_col], classes)
        lookup[key] = pmf
        cells.append(
            {
                "previous_activity": key,
                "source_n": int(len(group)),
                "probabilities": pmf.tolist(),
            }
        )
    probs = np.vstack(
        [lookup.get(_as_category(value), global_pmf) for value in merged["prefix_last_activity"]]
    )
    assert_pmf(probs)
    model = {
        "model_type": "WEIGHTED_FIRST_ORDER_TRANSITION_MATRIX_V1",
        "fit_partition": "TRAIN",
        "weight": "W_GEW",
        "target": "target_destination_activity",
        "conditioning": ["prefix_last_activity"],
        "activity_support": classes,
        "cells": cells,
        "global_fallback_probabilities": global_pmf.tolist(),
        "return_home_forced": False,
    }
    return model, probs


def build_chain_backoff_model(
    merged: pd.DataFrame,
    hierarchy: list[list[str]],
    classes: list[str],
    min_n: int,
    alpha: float,
) -> tuple[dict[str, Any], np.ndarray, pd.DataFrame]:
    if alpha <= 0:
        raise ValueError("Dirichlet alpha must be positive")
    levels: list[dict[str, Any]] = []
    lookups: list[dict[tuple[str, ...], dict[str, Any]]] = []
    for level_index, dimensions in enumerate(hierarchy, start=1):
        cells: list[dict[str, Any]] = []
        lookup: dict[tuple[str, ...], dict[str, Any]] = {}
        if dimensions == [GLOBAL_TOKEN]:
            groups = [((GLOBAL_TOKEN,), merged)]
        else:
            group_arg: str | list[str] = dimensions[0] if len(dimensions) == 1 else dimensions
            groups = []
            for raw_key, group in merged.groupby(group_arg, sort=True, dropna=False):
                raw_tuple = raw_key if isinstance(raw_key, tuple) else (raw_key,)
                key = tuple(_as_category(value) for value in raw_tuple)
                groups.append((key, group))
        for key, group in groups:
            source_n = int(len(group))
            is_global = dimensions == [GLOBAL_TOKEN]
            eligible = is_global or source_n >= min_n
            pmf = weighted_categorical_pmf(
                group["target_destination_activity"],
                group["fit_weight_W_GEW"],
                classes,
                alpha=alpha,
            )
            cell = {
                "key": _serialize_key(dimensions, key),
                "source_n": source_n,
                "low_n": False if is_global else source_n < min_n,
                "eligible_direct": bool(eligible),
                "probabilities": pmf.tolist(),
            }
            cells.append(cell)
            lookup[key] = cell
        levels.append(
            {
                "level": level_index,
                "dimensions": dimensions,
                "cells": cells,
            }
        )
        lookups.append(lookup)

    selected_levels = np.zeros(len(merged), dtype=np.int64)
    probs = np.zeros((len(merged), len(classes)), dtype=np.float64)
    for row_pos, (_, row) in enumerate(merged.iterrows()):
        selected: dict[str, Any] | None = None
        selected_level = 0
        for level_index, (dimensions, lookup) in enumerate(zip(hierarchy, lookups, strict=True), start=1):
            key = _cell_key(row, dimensions)
            cell = lookup.get(key)
            if cell is not None and bool(cell["eligible_direct"]):
                selected = cell
                selected_level = level_index
                break
        if selected is None:
            raise ValueError("CHAIN_BACKOFF_V1 failed to resolve a TRAIN row")
        probs[row_pos] = np.asarray(selected["probabilities"], dtype=float)
        selected_levels[row_pos] = selected_level
    assert_pmf(probs)

    summary_rows: list[dict[str, Any]] = []
    for level in levels:
        cells = level["cells"]
        idx = int(level["level"])
        summary_rows.append(
            {
                "level": idx,
                "dimensions": "+".join(level["dimensions"]),
                "cells_total": len(cells),
                "cells_eligible_direct": sum(bool(cell["eligible_direct"]) for cell in cells),
                "cells_low_n": sum(bool(cell["low_n"]) for cell in cells),
                "train_rows_selected": int(np.sum(selected_levels == idx)),
            }
        )

    model = {
        "model_type": "TERMINAL_AWARE_VARIABLE_ORDER_MARKOV_NGRAM_WITH_BACKOFF_V1",
        "fit_partition": "TRAIN",
        "hierarchy_id": "CHAIN_BACKOFF_V1",
        "hierarchy": hierarchy,
        "support_count_basis": "RAW_STRICT_TRAIN_ROWS_BEFORE_WEIGHTING",
        "direct_support_min_n": int(min_n),
        "low_n_rule": f"source_n < {int(min_n)}",
        "probability_weight": "W_GEW",
        "dirichlet_alpha": float(alpha),
        "activity_support": classes,
        "levels": levels,
        "start_token": START_TOKEN,
        "remaining_trips_semantics": "generated_trip_count-current_trip_index",
        "return_home_forced": False,
    }
    return model, probs, pd.DataFrame(summary_rows)


def _multinomial_logits(
    params: np.ndarray,
    x: np.ndarray,
    n_classes: int,
) -> np.ndarray:
    n_features = x.shape[1]
    beta = params.reshape(n_classes - 1, n_features + 1)
    logits_nonref = beta[:, 0][np.newaxis, :] + x @ beta[:, 1:].T
    logits = np.zeros((len(x), n_classes), dtype=np.float64)
    logits[:, 1:] = logits_nonref
    return logits


def _multinomial_objective_gradient(
    params: np.ndarray,
    x: np.ndarray,
    y: np.ndarray,
    w: np.ndarray,
    n_classes: int,
    lambda_l2: float,
) -> tuple[float, np.ndarray]:
    logits = _multinomial_logits(params, x, n_classes)
    log_probs = logits - logsumexp(logits, axis=1, keepdims=True)
    probs = np.exp(log_probs)
    normalized_w = w / np.sum(w)
    nll = float(np.sum(normalized_w * (-log_probs[np.arange(len(y)), y])))

    n_features = x.shape[1]
    beta = params.reshape(n_classes - 1, n_features + 1)
    penalty = 0.5 * float(lambda_l2) * float(np.sum(beta[:, 1:] ** 2))
    objective = nll + penalty

    indicator = np.zeros_like(probs)
    indicator[np.arange(len(y)), y] = 1.0
    error = (probs - indicator)[:, 1:] * normalized_w[:, np.newaxis]
    grad = np.zeros_like(beta)
    grad[:, 0] = np.sum(error, axis=0)
    grad[:, 1:] = error.T @ x + float(lambda_l2) * beta[:, 1:]
    return objective, grad.ravel()


def fit_multinomial_l2(
    data: EncodedChainData,
    lambda_l2: float,
    maxiter: int,
    ftol: float,
    gtol: float,
    coefficient_bounds: tuple[float, float],
    reject_if_boundary_hit: bool,
) -> tuple[dict[str, Any], np.ndarray]:
    n_classes = len(data.target_classes)
    n_features = data.x.shape[1]
    initial = np.zeros((n_classes - 1) * (n_features + 1), dtype=np.float64)
    bounds = [coefficient_bounds] * len(initial)

    def objective(params: np.ndarray) -> tuple[float, np.ndarray]:
        return _multinomial_objective_gradient(
            params,
            data.x,
            data.y,
            data.w,
            n_classes,
            lambda_l2,
        )

    result = minimize(
        objective,
        initial,
        method="L-BFGS-B",
        jac=True,
        bounds=bounds,
        options={"maxiter": int(maxiter), "ftol": float(ftol), "gtol": float(gtol)},
    )
    if not result.success:
        raise RuntimeError(f"CHAIN_B optimizer failed: {result.message}")
    low, high = coefficient_bounds
    boundary_hit = bool(np.any(np.isclose(result.x, low)) or np.any(np.isclose(result.x, high)))
    if reject_if_boundary_hit and boundary_hit:
        raise RuntimeError("CHAIN_B optimizer hit frozen coefficient bounds")

    logits = _multinomial_logits(result.x, data.x, n_classes)
    log_probs = logits - logsumexp(logits, axis=1, keepdims=True)
    probs = np.exp(log_probs)
    assert_pmf(probs)
    beta = result.x.reshape(n_classes - 1, n_features + 1)
    model = {
        "model_type": "REGULARIZED_MULTINOMIAL_LOGISTIC_NEXT_ACTIVITY_V1",
        "fit_partition": "TRAIN",
        "fit_objective": "WEIGHTED_MEAN_MULTINOMIAL_CROSS_ENTROPY_PLUS_L2",
        "lambda_l2": float(lambda_l2),
        "intercept_penalized": False,
        "coefficients_penalized": True,
        "reference_target_class": data.target_classes[0],
        "target_classes": data.target_classes,
        "feature_names": data.feature_names,
        "intercepts_nonreference": beta[:, 0].tolist(),
        "coefficients_nonreference": beta[:, 1:].tolist(),
        "optimizer": {
            "method": "scipy_L-BFGS-B",
            "success": bool(result.success),
            "message": str(result.message),
            "iterations": int(result.nit),
            "objective": float(result.fun),
            "boundary_hit": boundary_hit,
            "coefficient_bounds": [float(low), float(high)],
        },
        "return_home_forced": False,
    }
    return model, probs


def training_metrics(
    merged: pd.DataFrame,
    classes: list[str],
    probs: np.ndarray,
) -> dict[str, float]:
    class_index = {value: i for i, value in enumerate(classes)}
    y = np.asarray([class_index[str(v)] for v in merged["target_destination_activity"]])
    w = merged["fit_weight_W_GEW"].astype(float).to_numpy()
    logloss = weighted_log_loss(y, probs, w)
    predicted = np.argmax(probs, axis=1)
    accuracy = float(np.average(predicted == y, weights=w))
    home_index = class_index.get("HOME")
    if home_index is None:
        raise ValueError("HOME must be present in activity support")
    observed_home = float(np.average(y == home_index, weights=w))
    predicted_home = float(np.average(probs[:, home_index], weights=w))
    final_mask = merged["remaining_trips"].astype(int).to_numpy() == 0
    if not np.any(final_mask):
        raise ValueError("No final transitions in TRAIN chain data")
    final_w = w[final_mask]
    observed_final_home = float(np.average(y[final_mask] == home_index, weights=final_w))
    predicted_final_home = float(np.average(probs[final_mask, home_index], weights=final_w))
    return {
        "weighted_next_activity_log_loss": logloss,
        "weighted_next_activity_accuracy_report_only": accuracy,
        "weighted_observed_home_transition_share": observed_home,
        "weighted_predicted_home_transition_probability": predicted_home,
        "weighted_observed_final_home_share": observed_final_home,
        "weighted_predicted_final_home_probability": predicted_final_home,
    }


def weighted_initial_activity_pmf(days: pd.DataFrame, classes: list[str]) -> dict[str, Any]:
    observed = sorted({str(value) for value in days["first_origin_activity"]})
    support = sorted(set(classes) | set(observed))
    pmf = weighted_categorical_pmf(
        days["first_origin_activity"],
        days["day_weight_P_GEW"],
        support,
    )
    return {
        "support": support,
        "probabilities": pmf.tolist(),
        "weight": "P_GEW",
        "fit_partition": "TRAIN",
    }


def generate_activity_chain(
    trip_count: int,
    first_activity: str,
    probability_callback: Callable[[list[str], int, int], tuple[list[str], np.ndarray]],
    rng: np.random.Generator,
) -> list[str]:
    if trip_count < 1:
        raise ValueError("Activity-chain generation requires positive K")
    activities = [str(first_activity)]
    for transition_index in range(1, trip_count + 1):
        remaining = trip_count - transition_index
        support, pmf = probability_callback(activities, remaining, transition_index)
        assert_pmf(np.asarray(pmf, dtype=float))
        next_activity = str(rng.choice(np.asarray(support, dtype=object), p=np.asarray(pmf)))
        activities.append(next_activity)
    if len(activities) != trip_count + 1:
        raise AssertionError("Generated chain must contain K+1 activity states")
    return activities
