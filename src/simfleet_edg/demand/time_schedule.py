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
MINUTES_PER_DAY = 1440


@dataclass(frozen=True)
class EncodedTimeData:
    x: np.ndarray
    w: np.ndarray
    departure: np.ndarray
    duration: np.ndarray
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


def validate_temporal_row(
    departure_clock_minute: float,
    duration_minute: float,
    *,
    previous_arrival_absolute_minute: float | None = None,
    trips_remaining_after_current: int | None = None,
) -> tuple[bool, dict[str, int | float]]:
    dep = float(departure_clock_minute)
    dur = float(duration_minute)
    if not math.isfinite(dep) or not math.isfinite(dur):
        return False, {}
    if dep < 0 or dep >= MINUTES_PER_DAY or dur < 1:
        return False, {}
    arrival_abs = dep + dur
    day_offset = int(math.floor(arrival_abs / MINUTES_PER_DAY))
    if day_offset not in {0, 1}:
        return False, {}
    arrival_clock = int(round(arrival_abs - day_offset * MINUTES_PER_DAY))
    if arrival_clock < 0 or arrival_clock >= MINUTES_PER_DAY:
        return False, {}
    if previous_arrival_absolute_minute is not None:
        prev = float(previous_arrival_absolute_minute)
        if not math.isfinite(prev) or dep < prev:
            return False, {}
    if trips_remaining_after_current is not None and trips_remaining_after_current > 0:
        if arrival_abs >= MINUTES_PER_DAY:
            return False, {}
    return True, {
        "departure_clock_minute": int(round(dep)),
        "arrival_clock_minute": arrival_clock,
        "arrival_day_offset": day_offset,
        "duration_from_clock_min": int(round(dur)),
        "arrival_absolute_minute": float(arrival_abs),
    }


def validate_source_temporal_targets(frame: pd.DataFrame) -> None:
    dep = frame["target_departure_clock_minute"].astype(float).to_numpy()
    arr = frame["target_arrival_clock_minute"].astype(float).to_numpy()
    offset = frame["target_arrival_day_offset"].astype(int).to_numpy()
    dur = frame["target_duration_from_clock_min"].astype(float).to_numpy()
    if not np.isfinite(dep).all() or not np.isfinite(arr).all() or not np.isfinite(dur).all():
        raise ValueError("Temporal targets must be finite")
    if np.any(dep < 0) or np.any(dep >= MINUTES_PER_DAY):
        raise ValueError("Departure clocks outside [0,1439]")
    if np.any(arr < 0) or np.any(arr >= MINUTES_PER_DAY):
        raise ValueError("Arrival clocks outside [0,1439]")
    if not set(np.unique(offset)).issubset({0, 1}):
        raise ValueError("Arrival day offsets must be 0/1")
    if np.any(dur < 1):
        raise ValueError("Duration must be >=1 minute")
    reconstructed = arr + MINUTES_PER_DAY * offset - dep
    if not np.allclose(reconstructed, dur, rtol=0.0, atol=1e-12):
        raise ValueError("Arrival/departure/day-offset/duration identity mismatch")


def load_train_time_tables(
    materialized_root: Path,
    expected_rows: int,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    context = pd.read_csv(materialized_root / "TRAIN" / "person_day_context.csv")
    time = pd.read_csv(materialized_root / "TRAIN" / "time_trips.csv")
    if len(time) != expected_rows:
        raise ValueError(f"Expected {expected_rows} TRAIN time rows, got {len(time)}")
    validate_source_temporal_targets(time)
    merged = time.merge(
        context,
        left_on="context_row_id",
        right_on="row_id",
        how="left",
        validate="many_to_one",
        suffixes=("_time", "_context"),
    )
    if merged["row_id"].isna().any():
        raise ValueError("Every time row must resolve to person_day_context")
    weights = merged["fit_weight_W_GEW"].astype(float).to_numpy()
    if not np.isfinite(weights).all() or np.any(weights <= 0):
        raise ValueError("W_GEW must be finite and strictly positive")
    return context, time, merged


def weighted_reference_temporal_support(merged: pd.DataFrame) -> dict[str, Any]:
    weights = merged["fit_weight_W_GEW"].astype(float).to_numpy()
    hours = (merged["target_departure_clock_minute"].astype(int).to_numpy() // 60).astype(int)
    hour_mass = np.bincount(hours, weights=weights, minlength=24).astype(float)
    hour_pmf = hour_mass / hour_mass.sum()
    tuples = (
        merged.assign(
            _dep=merged["target_departure_clock_minute"].astype(int),
            _dur=merged["target_duration_from_clock_min"].astype(int),
        )
        .groupby(["_dep", "_dur"], sort=True, dropna=False)["fit_weight_W_GEW"]
        .agg(["count", "sum"])
        .reset_index()
    )
    total = float(tuples["sum"].sum())
    support = [
        {
            "departure_clock_minute": int(dep),
            "duration_from_clock_min": int(dur),
            "source_n": int(count),
            "weight_mass": float(weight_mass),
            "probability": float(weight_mass / total),
        }
        for dep, dur, count, weight_mass in tuples.itertuples(index=False, name=None)
    ]
    return {
        "model_type": "WEIGHTED_GLOBAL_EMPIRICAL_TEMPORAL_REFERENCE_V1",
        "fit_partition": "TRAIN",
        "primary_reference_marginal": "WEIGHTED_DEPARTURE_HOUR_EMPIRICAL_DISTRIBUTION",
        "departure_hour_probabilities": hour_pmf.tolist(),
        "joint_temporal_support": support,
        "probability_weight": "W_GEW",
        "train_rows": int(len(merged)),
        "temporal_invariant_policy": "REJECT_INVALID_DRAW_NO_SILENT_REPAIR",
        "arrival_reconstruction": "departure_clock_minute + duration_from_clock_min",
    }


def _group_key(row: pd.Series | dict[str, Any], dimensions: list[str]) -> tuple[str, ...]:
    if dimensions == [GLOBAL_TOKEN]:
        return (GLOBAL_TOKEN,)
    return tuple(_as_category(row[d]) for d in dimensions)


def _serialize_key(dimensions: list[str], key: tuple[str, ...]) -> dict[str, str]:
    if dimensions == [GLOBAL_TOKEN]:
        return {GLOBAL_TOKEN: GLOBAL_TOKEN}
    return dict(zip(dimensions, key, strict=True))


def _cell_from_group(group: pd.DataFrame, dimensions: list[str], key: tuple[str, ...], min_n: int) -> dict[str, Any]:
    source_n = int(len(group))
    agg = (
        group.assign(
            _dep=group["target_departure_clock_minute"].astype(int),
            _dur=group["target_duration_from_clock_min"].astype(int),
        )
        .groupby(["_dep", "_dur"], sort=True)["fit_weight_W_GEW"]
        .agg(["count", "sum"])
        .reset_index()
    )
    total = float(agg["sum"].sum())
    samples = [
        {
            "departure_clock_minute": int(dep),
            "duration_from_clock_min": int(dur),
            "source_n": int(count),
            "weight_mass": float(weight_mass),
            "probability": float(weight_mass / total),
        }
        for dep, dur, count, weight_mass in agg.itertuples(index=False, name=None)
    ]
    global_level = dimensions == [GLOBAL_TOKEN]
    return {
        "key": _serialize_key(dimensions, key),
        "source_n": source_n,
        "low_n": False if global_level else source_n < min_n,
        "eligible_direct": True if global_level else source_n >= min_n,
        "samples": samples,
    }


def build_time_backoff_model(
    merged: pd.DataFrame,
    hierarchy: list[list[str]],
    *,
    bandwidth_minutes: int,
    min_n: int,
    max_rejection_attempts: int,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    levels: list[dict[str, Any]] = []
    cell_lookup: list[dict[tuple[str, ...], dict[str, Any]]] = []
    for level_index, dimensions in enumerate(hierarchy, start=1):
        if dimensions == [GLOBAL_TOKEN]:
            groups = [((GLOBAL_TOKEN,), merged)]
        else:
            work = merged.copy()
            for column in dimensions:
                work[column] = work[column].map(_as_category)
            groups = list(work.groupby(dimensions, sort=True, dropna=False))
            normalized: list[tuple[tuple[str, ...], pd.DataFrame]] = []
            for key, group in groups:
                if not isinstance(key, tuple):
                    key = (key,)
                normalized.append((tuple(str(v) for v in key), group))
            groups = normalized
        cells = [_cell_from_group(group, dimensions, key, min_n) for key, group in groups]
        lookup = {tuple(cell["key"].values()): cell for cell in cells}
        cell_lookup.append(lookup)
        levels.append({"level": level_index, "dimensions": dimensions, "cells": cells})

    selected_counts = [0 for _ in hierarchy]
    for _, row in merged.iterrows():
        for idx, dimensions in enumerate(hierarchy):
            key = _group_key(row, dimensions)
            cell = cell_lookup[idx][key]
            if cell["eligible_direct"]:
                selected_counts[idx] += 1
                break
        else:
            raise RuntimeError("Global timing backoff failed to resolve TRAIN row")

    summary = []
    for level, selected in zip(levels, selected_counts, strict=True):
        cells = level["cells"]
        summary.append(
            {
                "level": int(level["level"]),
                "dimensions": "+".join(level["dimensions"]),
                "cells_total": len(cells),
                "cells_eligible_direct": sum(bool(c["eligible_direct"]) for c in cells),
                "cells_low_n": sum(bool(c["low_n"]) for c in cells),
                "train_rows_selected": int(selected),
            }
        )

    model = {
        "model_type": "WEIGHTED_CONDITIONAL_EMPIRICAL_TEMPORAL_KERNEL_WITH_BACKOFF_V1",
        "fit_partition": "TRAIN",
        "hierarchy_id": "TIME_BACKOFF_V1",
        "support_count_basis": "RAW_STRICT_TRAIN_ROWS_BEFORE_WEIGHTING",
        "direct_support_min_n": int(min_n),
        "low_n_rule": f"source_n < {min_n}",
        "probability_weight": "W_GEW",
        "departure_kernel_shape": "DISCRETE_CIRCULAR_UNIFORM_INTEGER_V1",
        "departure_kernel_bandwidth_minutes": int(bandwidth_minutes),
        "duration_coupling": "EMPIRICAL_JOINT_DONOR_DURATION",
        "arrival_reconstruction": "departure_clock_minute + duration_from_clock_min",
        "max_rejection_attempts_per_level": int(max_rejection_attempts),
        "rejection_policy": "REJECT_THEN_DETERMINISTIC_BACKOFF_NO_CLOCK_REPAIR",
        "levels": levels,
    }
    return model, summary


def _weighted_choice_index(probabilities: np.ndarray, rng: np.random.Generator) -> int:
    p = np.asarray(probabilities, dtype=float)
    if not np.isfinite(p).all() or np.any(p < 0) or p.sum() <= 0:
        raise ValueError("Invalid weighted probabilities")
    p = p / p.sum()
    return int(rng.choice(len(p), p=p))


def sample_time_a(
    model: dict[str, Any],
    state: dict[str, Any],
    *,
    previous_arrival_absolute_minute: float | None,
    trips_remaining_after_current: int,
    seed: int,
) -> dict[str, Any]:
    rng = np.random.default_rng(seed)
    bandwidth = int(model["departure_kernel_bandwidth_minutes"])
    max_attempts = int(model["max_rejection_attempts_per_level"])
    for level in model["levels"]:
        dimensions = list(level["dimensions"])
        requested = _group_key(state, dimensions)
        matched = None
        for cell in level["cells"]:
            if tuple(cell["key"].values()) == requested:
                matched = cell
                break
        if matched is None or not matched["eligible_direct"]:
            continue
        samples = matched["samples"]
        probabilities = np.asarray([float(s["probability"]) for s in samples], dtype=float)
        for attempt in range(1, max_attempts + 1):
            sample = samples[_weighted_choice_index(probabilities, rng)]
            base_dep = int(sample["departure_clock_minute"])
            if bandwidth:
                jitter = int(rng.integers(-bandwidth, bandwidth + 1))
            else:
                jitter = 0
            departure = (base_dep + jitter) % MINUTES_PER_DAY
            duration = int(sample["duration_from_clock_min"])
            ok, result = validate_temporal_row(
                departure,
                duration,
                previous_arrival_absolute_minute=previous_arrival_absolute_minute,
                trips_remaining_after_current=trips_remaining_after_current,
            )
            if ok:
                return {
                    **result,
                    "selected_level": int(level["level"]),
                    "source_n": int(matched["source_n"]),
                    "attempt": attempt,
                    "jitter_minute": jitter,
                }
    raise RuntimeError("TIME_A exhausted deterministic backoff without a valid temporal draw")


def _train_categories(series: pd.Series) -> list[str]:
    observed = sorted({_as_category(v) for v in series.tolist()})
    for token in (RESERVED_MISSING, RESERVED_UNSEEN):
        if token not in observed:
            observed.append(token)
    return observed


def build_time_b_encoder_manifest(
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


def transform_time_b_context(
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
        mapped = [v if v in index else RESERVED_UNSEEN for v in values]
        unseen_counts[column] = sum(v == RESERVED_UNSEEN for v in mapped)
        block = np.zeros((len(frame), len(categories)), dtype=np.float64)
        rows = np.arange(len(frame))
        cols = np.asarray([index.get(v, unseen_idx) for v in mapped], dtype=np.int64)
        block[rows, cols] = 1.0
        blocks.append(block)
    for column in encoder["numeric_columns"]:
        values = pd.to_numeric(frame[column], errors="coerce").astype(float).to_numpy()
        blocks.append(values[:, np.newaxis])
    return np.concatenate(blocks, axis=1), unseen_counts


def encode_time_b_train(
    merged: pd.DataFrame,
    categorical_columns: list[str],
    numeric_columns: list[str],
) -> EncodedTimeData:
    encoder = build_time_b_encoder_manifest(merged, categorical_columns, numeric_columns)
    x, unseen = transform_time_b_context(merged, encoder)
    if any(unseen.values()):
        raise ValueError("TRAIN TIME_B encoder generated unseen categories from TRAIN")
    w = merged["fit_weight_W_GEW"].astype(float).to_numpy()
    departure = merged["target_departure_clock_minute"].astype(float).to_numpy()
    duration = merged["target_duration_from_clock_min"].astype(float).to_numpy()
    return EncodedTimeData(
        x=x,
        w=w,
        departure=departure,
        duration=duration,
        merged=merged,
        feature_names=list(encoder["feature_names"]),
        encoder_manifest=encoder,
    )


def feature_matrix_sha256(data: EncodedTimeData) -> str:
    h = hashlib.sha256()
    h.update(np.ascontiguousarray(data.x, dtype="<f8").tobytes())
    h.update(np.ascontiguousarray(data.departure, dtype="<f8").tobytes())
    h.update(np.ascontiguousarray(data.duration, dtype="<f8").tobytes())
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
    data: EncodedTimeData,
    *,
    common: dict[str, Any],
    grid: dict[str, Any],
    quantiles: list[float],
    seed: int,
) -> tuple[dict[str, Any], dict[str, np.ndarray]]:
    frame = pd.DataFrame(data.x, columns=data.feature_names)
    model_payload: dict[str, Any] = {}
    predictions: dict[str, np.ndarray] = {}
    for target_name, target in (
        ("departure_clock_minute", data.departure),
        ("duration_from_clock_min", data.duration),
    ):
        target_models: dict[str, Any] = {}
        target_predictions: list[np.ndarray] = []
        for q in quantiles:
            derived_seed = int((seed + round(q * 10000) + (0 if target_name.startswith("departure") else 1000003)) % (2**32))
            params = quantile_parameters(common, grid, q, derived_seed)
            reg = lgb.LGBMRegressor(**params)
            reg.fit(frame, target, sample_weight=data.w)
            pred = reg.predict(frame).astype(float)
            if not np.isfinite(pred).all():
                raise ValueError("TIME_B produced non-finite TRAIN quantile prediction")
            target_predictions.append(pred)
            target_models[f"q{q:.2f}"] = {
                "quantile": float(q),
                "parameters": params,
                "booster_model_string": reg.booster_.model_to_string(),
                "num_trees": int(reg.booster_.num_trees()),
            }
        raw = np.column_stack(target_predictions)
        repaired = np.maximum.accumulate(raw, axis=1)
        predictions[f"{target_name}_raw"] = raw
        predictions[f"{target_name}_repaired"] = repaired
        model_payload[target_name] = target_models
    return model_payload, predictions


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
    values = [weighted_pinball(y, prediction_matrix[:, i], q, weights) for i, q in enumerate(quantiles)]
    return float(np.mean(values))


def time_b_training_metrics(
    data: EncodedTimeData,
    predictions: dict[str, np.ndarray],
    quantiles: list[float],
) -> dict[str, float]:
    dep = predictions["departure_clock_minute_repaired"]
    dur = predictions["duration_from_clock_min_repaired"]
    dep_loss = multi_quantile_pinball(data.departure, dep, quantiles, data.w)
    dur_loss = multi_quantile_pinball(data.duration, dur, quantiles, data.w)
    median_index = quantiles.index(0.5)
    return {
        "weighted_multi_quantile_pinball_departure": dep_loss,
        "weighted_multi_quantile_pinball_duration": dur_loss,
        "weighted_multi_quantile_pinball_combined": 0.5 * (dep_loss + dur_loss),
        "weighted_observed_mean_departure_minute": float(np.average(data.departure, weights=data.w)),
        "weighted_predicted_median_departure_minute": float(np.average(dep[:, median_index], weights=data.w)),
        "weighted_observed_mean_duration_minute": float(np.average(data.duration, weights=data.w)),
        "weighted_predicted_median_duration_minute": float(np.average(dur[:, median_index], weights=data.w)),
    }


def finite_metrics(metrics: dict[str, float]) -> bool:
    return all(math.isfinite(float(value)) for value in metrics.values())
