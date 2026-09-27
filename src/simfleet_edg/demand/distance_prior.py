from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import lightgbm as lgb
import numpy as np
import pandas as pd

RESERVED_UNSEEN = "__UNSEEN__"
RESERVED_MISSING = "__MISSING_CONTEXT__"
GLOBAL_TOKEN = "GLOBAL"


@dataclass(frozen=True)
class EncodedDistanceData:
    x: np.ndarray
    w: np.ndarray
    target: np.ndarray
    merged: pd.DataFrame
    feature_names: list[str]
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


def validate_distance_targets(frame: pd.DataFrame, target_column: str = "target_distance_prior_km") -> None:
    target = pd.to_numeric(frame[target_column], errors="coerce").astype(float).to_numpy()
    if not np.isfinite(target).all():
        raise ValueError("Distance target must be finite")
    if np.any(target <= 0):
        raise ValueError("Distance target must be strictly positive")


def load_train_distance_tables(
    materialized_root: Path,
    expected_rows: int,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    context = pd.read_csv(materialized_root / "TRAIN" / "person_day_context.csv")
    distance = pd.read_csv(materialized_root / "TRAIN" / "distance_raw.csv")
    if len(distance) != expected_rows:
        raise ValueError(f"Expected {expected_rows} TRAIN raw-distance rows, got {len(distance)}")
    validate_distance_targets(distance)
    merged = distance.merge(
        context,
        left_on="context_row_id",
        right_on="row_id",
        how="left",
        validate="many_to_one",
        suffixes=("_distance", "_context"),
    )
    if merged["row_id"].isna().any():
        raise ValueError("Every raw-distance row must resolve to person_day_context")
    weights = merged["fit_weight_W_GEW"].astype(float).to_numpy()
    if not np.isfinite(weights).all() or np.any(weights <= 0):
        raise ValueError("W_GEW must be finite and strictly positive")
    return context, distance, merged


def _weighted_support(frame: pd.DataFrame, target_column: str) -> list[dict[str, Any]]:
    agg = (
        frame.assign(_target=pd.to_numeric(frame[target_column], errors="raise").astype(float))
        .groupby("_target", sort=True)["fit_weight_W_GEW"]
        .agg(["count", "sum"])
        .reset_index()
    )
    total = float(agg["sum"].sum())
    cumulative = 0.0
    support: list[dict[str, Any]] = []
    for distance_km, source_n, weight_mass in agg.itertuples(index=False, name=None):
        cumulative += float(weight_mass) / total
        support.append(
            {
                "distance_km": float(distance_km),
                "source_n": int(source_n),
                "weight_mass": float(weight_mass),
                "probability": float(weight_mass / total),
                "cumulative_probability": float(cumulative),
            }
        )
    if support:
        support[-1]["cumulative_probability"] = 1.0
    return support


def inverse_ecdf_value(support: list[dict[str, Any]], uniform: float) -> float:
    if not support:
        raise ValueError("Inverse ECDF support is empty")
    u = float(uniform)
    if not math.isfinite(u) or u < 0 or u > 1:
        raise ValueError("uniform must be finite and inside [0,1]")
    distances = np.asarray([float(row["distance_km"]) for row in support], dtype=float)
    cumulative = np.asarray([float(row["cumulative_probability"]) for row in support], dtype=float)
    xp = np.concatenate(([0.0], cumulative))
    fp = np.concatenate(([distances[0]], distances))
    return float(np.interp(u, xp, fp))


def weighted_reference_distance_support(merged: pd.DataFrame) -> dict[str, Any]:
    support = _weighted_support(merged, "target_distance_prior_km")
    return {
        "model_type": "WEIGHTED_UNCONDITIONAL_RAW_WEGKM_ECDF_V1",
        "fit_partition": "TRAIN",
        "target": "RAW_WEGKM",
        "target_column": "target_distance_prior_km",
        "probability_weight": "W_GEW",
        "inverse_ecdf_policy": "LINEAR_WEIGHTED_CUMULATIVE_MASS_KNOTS_V1",
        "support": support,
        "train_rows": int(len(merged)),
        "target_min_km": float(merged["target_distance_prior_km"].min()),
        "target_max_km": float(merged["target_distance_prior_km"].max()),
        "distance_semantics": "M2_PATH_LENGTH_PRIOR_FOR_M3_NOT_EXACT_OD_OR_ROUTED_DISTANCE",
    }


def _group_key(row: pd.Series | dict[str, Any], dimensions: list[str]) -> tuple[str, ...]:
    if dimensions == [GLOBAL_TOKEN]:
        return (GLOBAL_TOKEN,)
    return tuple(_as_category(row[d]) for d in dimensions)


def _serialize_key(dimensions: list[str], key: tuple[str, ...]) -> dict[str, str]:
    if dimensions == [GLOBAL_TOKEN]:
        return {GLOBAL_TOKEN: GLOBAL_TOKEN}
    return dict(zip(dimensions, key, strict=True))


def _cell_from_group(
    group: pd.DataFrame,
    dimensions: list[str],
    key: tuple[str, ...],
    min_n: int,
) -> dict[str, Any]:
    source_n = int(len(group))
    global_level = dimensions == [GLOBAL_TOKEN]
    return {
        "key": _serialize_key(dimensions, key),
        "source_n": source_n,
        "low_n": False if global_level else source_n < min_n,
        "eligible_direct": True if global_level else source_n >= min_n,
        "support": _weighted_support(group, "target_distance_prior_km"),
    }


def build_distance_backoff_model(
    merged: pd.DataFrame,
    hierarchy: list[list[str]],
    *,
    min_n: int,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    levels: list[dict[str, Any]] = []
    cell_lookup: list[dict[tuple[str, ...], dict[str, Any]]] = []
    for level_index, dimensions in enumerate(hierarchy, start=1):
        if dimensions == [GLOBAL_TOKEN]:
            groups: list[tuple[tuple[str, ...], pd.DataFrame]] = [((GLOBAL_TOKEN,), merged)]
        else:
            work = merged.copy()
            for column in dimensions:
                work[column] = work[column].map(_as_category)
            grouped = work.groupby(dimensions, sort=True, dropna=False)
            groups = []
            for key, group in grouped:
                if not isinstance(key, tuple):
                    key = (key,)
                groups.append((tuple(str(v) for v in key), group))
        cells = [_cell_from_group(group, dimensions, key, min_n) for key, group in groups]
        lookup = {tuple(cell["key"].values()): cell for cell in cells}
        cell_lookup.append(lookup)
        levels.append({"level": level_index, "dimensions": dimensions, "cells": cells})

    selected_counts = [0 for _ in hierarchy]
    for _, row in merged.iterrows():
        for idx, dimensions in enumerate(hierarchy):
            key = _group_key(row, dimensions)
            cell = cell_lookup[idx].get(key)
            if cell is not None and cell["eligible_direct"]:
                selected_counts[idx] += 1
                break
        else:
            raise RuntimeError("Global distance backoff failed to resolve TRAIN row")

    summary = []
    for idx, level in enumerate(levels):
        cells = level["cells"]
        summary.append(
            {
                "level": int(level["level"]),
                "dimensions": "+".join(level["dimensions"]),
                "cells_total": int(len(cells)),
                "cells_eligible_direct": int(sum(bool(cell["eligible_direct"]) for cell in cells)),
                "cells_low_n": int(sum(bool(cell["low_n"]) for cell in cells)),
                "train_rows_selected": int(selected_counts[idx]),
            }
        )

    return (
        {
            "model_type": "WEIGHTED_CONDITIONAL_INVERSE_ECDF_RAW_WEGKM_WITH_BACKOFF_V1",
            "fit_partition": "TRAIN",
            "target": "RAW_WEGKM",
            "target_column": "target_distance_prior_km",
            "probability_weight": "W_GEW",
            "hierarchy_id": "DIST_BACKOFF_V1",
            "support_count_basis": "RAW_STRICT_TRAIN_ROWS_BEFORE_WEIGHTING",
            "direct_support_min_n": int(min_n),
            "inverse_ecdf_policy": "LINEAR_WEIGHTED_CUMULATIVE_MASS_KNOTS_V1",
            "levels": levels,
            "train_rows": int(len(merged)),
            "distance_semantics": "M2_PATH_LENGTH_PRIOR_FOR_M3_NOT_EXACT_OD_OR_ROUTED_DISTANCE",
        },
        summary,
    )


def sample_distance_a(model: dict[str, Any], state: dict[str, Any], *, seed: int) -> dict[str, Any]:
    rng = np.random.default_rng(seed)
    trace: list[dict[str, Any]] = []
    for level in model["levels"]:
        dimensions = list(level["dimensions"])
        requested = _group_key(state, dimensions)
        matched = None
        for cell in level["cells"]:
            if tuple(cell["key"].values()) == requested:
                matched = cell
                break
        trace.append(
            {
                "level": int(level["level"]),
                "requested_key": _serialize_key(dimensions, requested),
                "source_n": None if matched is None else int(matched["source_n"]),
                "eligible_direct": False if matched is None else bool(matched["eligible_direct"]),
            }
        )
        if matched is None or not matched["eligible_direct"]:
            continue
        uniform = float(rng.random())
        return {
            "distance_prior_km": inverse_ecdf_value(matched["support"], uniform),
            "selected_level": int(level["level"]),
            "source_n": int(matched["source_n"]),
            "requested_key": _serialize_key(dimensions, requested),
            "draw_uniform": uniform,
            "backoff_trace": trace,
        }
    raise RuntimeError("DIST_A exhausted deterministic backoff")


def _train_categories(series: pd.Series) -> list[str]:
    observed = sorted({_as_category(v) for v in series.tolist()})
    for token in (RESERVED_MISSING, RESERVED_UNSEEN):
        if token not in observed:
            observed.append(token)
    return observed


def build_distance_b_encoder_manifest(
    train: pd.DataFrame,
    categorical_columns: list[str],
    numeric_columns: list[str],
) -> dict[str, Any]:
    categories = {column: _train_categories(train[column]) for column in categorical_columns}
    feature_names = [
        f"{column}=={value}" for column in categorical_columns for value in categories[column]
    ]
    feature_names.extend(f"raw__{column}" for column in numeric_columns)
    return {
        "encoder": "DETERMINISTIC_FULL_ONE_HOT_PLUS_RAW_NUMERIC_V1",
        "fit_partition": "TRAIN",
        "categorical_columns": categorical_columns,
        "numeric_columns": numeric_columns,
        "categories": categories,
        "feature_names": feature_names,
        "unknown_token": RESERVED_UNSEEN,
        "missing_token": RESERVED_MISSING,
        "numeric_missing_policy": "NATIVE_NAN_LIGHTGBM",
        "rare_pooling": "NONE",
    }


def transform_distance_b_context(
    frame: pd.DataFrame,
    encoder: dict[str, Any],
) -> tuple[np.ndarray, dict[str, int]]:
    blocks: list[np.ndarray] = []
    unseen_counts: dict[str, int] = {}
    for column in encoder["categorical_columns"]:
        categories = list(encoder["categories"][column])
        index = {value: idx for idx, value in enumerate(categories)}
        unseen_idx = index[RESERVED_UNSEEN]
        values = [_as_category(v) for v in frame[column].tolist()]
        mapped = [value if value in index else RESERVED_UNSEEN for value in values]
        unseen_counts[column] = sum(value == RESERVED_UNSEEN for value in mapped)
        block = np.zeros((len(frame), len(categories)), dtype=np.float64)
        rows = np.arange(len(frame))
        cols = np.asarray([index.get(value, unseen_idx) for value in mapped], dtype=np.int64)
        block[rows, cols] = 1.0
        blocks.append(block)
    for column in encoder["numeric_columns"]:
        values = pd.to_numeric(frame[column], errors="coerce").astype(float).to_numpy()
        blocks.append(values[:, np.newaxis])
    return np.concatenate(blocks, axis=1), unseen_counts


def encode_distance_b_train(
    merged: pd.DataFrame,
    categorical_columns: list[str],
    numeric_columns: list[str],
) -> EncodedDistanceData:
    encoder = build_distance_b_encoder_manifest(merged, categorical_columns, numeric_columns)
    x, unseen = transform_distance_b_context(merged, encoder)
    if any(unseen.values()):
        raise ValueError("TRAIN DIST_B encoder generated unseen categories from TRAIN")
    w = merged["fit_weight_W_GEW"].astype(float).to_numpy()
    target = merged["target_distance_prior_km"].astype(float).to_numpy()
    return EncodedDistanceData(
        x=x,
        w=w,
        target=target,
        merged=merged,
        feature_names=list(encoder["feature_names"]),
        encoder_manifest=encoder,
    )


def feature_matrix_sha256(data: EncodedDistanceData) -> str:
    h = hashlib.sha256()
    h.update(np.ascontiguousarray(data.x, dtype="<f8").tobytes())
    h.update(np.ascontiguousarray(data.target, dtype="<f8").tobytes())
    h.update(np.ascontiguousarray(data.w, dtype="<f8").tobytes())
    return h.hexdigest()


def quantile_parameters(common: dict[str, Any], grid: dict[str, Any], q: float, seed: int) -> dict[str, Any]:
    return {
        "objective": "quantile",
        "alpha": float(q),
        "learning_rate": float(common["learning_rate"]),
        "n_estimators": int(common["n_estimators"]),
        "max_depth": int(grid["max_depth"]),
        "num_leaves": int(grid["num_leaves"]),
        "min_child_samples": int(grid["min_data_in_leaf"]),
        "reg_lambda": float(grid["lambda_l2"]),
        "feature_fraction": 1.0,
        "bagging_fraction": 1.0,
        "bagging_freq": 0,
        "deterministic": True,
        "force_col_wise": True,
        "n_jobs": 1,
        "random_state": int(seed),
        "verbosity": -1,
    }


def fit_quantile_models(
    data: EncodedDistanceData,
    *,
    common: dict[str, Any],
    grid: dict[str, Any],
    quantiles: list[float],
    seed: int,
) -> tuple[dict[str, Any], np.ndarray]:
    frame = pd.DataFrame(data.x, columns=data.feature_names)
    target_predictions: list[np.ndarray] = []
    model_payload: dict[str, Any] = {}
    for q in quantiles:
        derived_seed = int((seed + round(q * 10000)) % (2**32))
        params = quantile_parameters(common, grid, q, derived_seed)
        reg = lgb.LGBMRegressor(**params)
        reg.fit(frame, data.target, sample_weight=data.w)
        pred = reg.predict(frame).astype(float)
        if not np.isfinite(pred).all():
            raise ValueError("DIST_B produced non-finite TRAIN quantile prediction")
        target_predictions.append(pred)
        model_payload[f"q{q:.2f}"] = {
            "quantile": float(q),
            "parameters": params,
            "booster_model_string": reg.booster_.model_to_string(),
            "num_trees": int(reg.booster_.num_trees()),
        }
    return model_payload, np.column_stack(target_predictions)


def repair_distance_quantiles(raw: np.ndarray, target_min: float, target_max: float) -> np.ndarray:
    clipped = np.clip(np.asarray(raw, dtype=float), float(target_min), float(target_max))
    return np.maximum.accumulate(clipped, axis=1)


def sample_distance_b(
    repaired_quantiles: np.ndarray,
    quantiles: list[float],
    *,
    uniform: float,
    target_min: float,
    target_max: float,
) -> float:
    values = np.asarray(repaired_quantiles, dtype=float)
    if values.ndim != 1 or len(values) != len(quantiles):
        raise ValueError("Expected one repaired value per quantile")
    if not np.all(np.diff(values) >= -1e-12):
        raise ValueError("Repaired distance quantiles must be monotone")
    u = float(uniform)
    if not math.isfinite(u) or u < 0 or u > 1:
        raise ValueError("uniform must be finite and inside [0,1]")
    xp = np.asarray([0.0, *quantiles, 1.0], dtype=float)
    fp = np.asarray([float(target_min), *values.tolist(), float(target_max)], dtype=float)
    if np.any(np.diff(fp) < -1e-12):
        raise ValueError("Distance reconstruction knots are not monotone")
    return float(np.interp(u, xp, fp))


def weighted_pinball(y: np.ndarray, pred: np.ndarray, q: float, weights: np.ndarray) -> float:
    residual = np.asarray(y, dtype=float) - np.asarray(pred, dtype=float)
    loss = np.maximum(q * residual, (q - 1.0) * residual)
    return float(np.average(loss, weights=weights))


def multi_quantile_pinball(
    y: np.ndarray,
    prediction_matrix: np.ndarray,
    quantiles: list[float],
    weights: np.ndarray,
) -> float:
    values = [
        weighted_pinball(y, prediction_matrix[:, idx], q, weights)
        for idx, q in enumerate(quantiles)
    ]
    return float(np.mean(values))


def weighted_quantile(values: np.ndarray, weights: np.ndarray, q: float) -> float:
    order = np.argsort(values, kind="mergesort")
    sorted_values = np.asarray(values, dtype=float)[order]
    sorted_weights = np.asarray(weights, dtype=float)[order]
    cumulative = np.cumsum(sorted_weights) / sorted_weights.sum()
    xp = np.concatenate(([0.0], cumulative))
    fp = np.concatenate(([sorted_values[0]], sorted_values))
    return float(np.interp(float(q), xp, fp))


def distance_b_training_metrics(
    data: EncodedDistanceData,
    raw_predictions: np.ndarray,
    repaired_predictions: np.ndarray,
    quantiles: list[float],
) -> dict[str, float]:
    median_index = quantiles.index(0.5)
    return {
        "weighted_multi_quantile_pinball_raw_km": multi_quantile_pinball(
            data.target, raw_predictions, quantiles, data.w
        ),
        "weighted_multi_quantile_pinball_repaired_km": multi_quantile_pinball(
            data.target, repaired_predictions, quantiles, data.w
        ),
        "weighted_observed_mean_km": float(np.average(data.target, weights=data.w)),
        "weighted_predicted_median_mean_km": float(
            np.average(repaired_predictions[:, median_index], weights=data.w)
        ),
        "weighted_observed_p50_km": weighted_quantile(data.target, data.w, 0.50),
        "weighted_observed_p90_km": weighted_quantile(data.target, data.w, 0.90),
        "weighted_observed_p95_km": weighted_quantile(data.target, data.w, 0.95),
    }


def finite_metrics(metrics: dict[str, float]) -> bool:
    return all(math.isfinite(float(value)) for value in metrics.values())
