from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from scipy.optimize import minimize
from scipy.special import digamma, gammaln, logsumexp

RESERVED_UNSEEN = "__UNSEEN__"
RESERVED_MISSING = "__MISSING_CONTEXT__"
GLOBAL_TOKEN = "GLOBAL"


@dataclass(frozen=True)
class EncodedCountData:
    x: np.ndarray
    y: np.ndarray
    k: np.ndarray
    w: np.ndarray
    source_rows: int
    feature_names: list[str]
    categories: dict[str, list[str]]
    reference_categories: dict[str, str]
    merged: pd.DataFrame
    k_min: int
    k_max: int


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def canonical_json_bytes(obj: Any) -> bytes:
    return (json.dumps(obj, sort_keys=True, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def fit_seed(master_seed: int, candidate_id: str, grid_id: str) -> int:
    payload = f"F3_1C|{master_seed}|{candidate_id}|{grid_id}|FIT".encode()
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


def build_count_a_encoder_manifest(
    train_context: pd.DataFrame,
    feature_columns: list[str],
) -> dict[str, Any]:
    categories: dict[str, list[str]] = {}
    references: dict[str, str] = {}
    feature_names: list[str] = []
    for column in feature_columns:
        observed = _observed_categories(train_context[column])
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
    return {
        "encoder": "DETERMINISTIC_REFERENCE_ONE_HOT_V1",
        "fit_partition": "TRAIN",
        "feature_columns": feature_columns,
        "categories": categories,
        "reference_categories": references,
        "feature_names": feature_names,
        "category_order": "CANONICAL_LEXICAL_OBSERVED_THEN_RESERVED_TOKENS",
        "reference_policy": "FIRST_OBSERVED_CANONICAL_CATEGORY_PER_FIELD",
        "unknown_token": RESERVED_UNSEEN,
        "missing_token": RESERVED_MISSING,
        "rare_pooling": "NONE",
    }


def transform_count_context(
    context: pd.DataFrame,
    encoder_manifest: dict[str, Any],
) -> tuple[np.ndarray, dict[str, int]]:
    blocks: list[np.ndarray] = []
    unseen_counts: dict[str, int] = {}
    categories: dict[str, list[str]] = encoder_manifest["categories"]
    references: dict[str, str] = encoder_manifest["reference_categories"]
    for column in encoder_manifest["feature_columns"]:
        full = categories[column]
        reference = references[column]
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
    if not blocks:
        return np.zeros((len(context), 0), dtype=np.float64), unseen_counts
    return np.concatenate(blocks, axis=1), unseen_counts


def load_train_trip_count(
    materialized_root: Path,
    feature_columns: list[str],
    expected_rows: int,
    expected_k_min: int,
    expected_k_max: int,
) -> tuple[EncodedCountData, dict[str, Any]]:
    context = pd.read_csv(materialized_root / "TRAIN" / "person_day_context.csv")
    target = pd.read_csv(materialized_root / "TRAIN" / "trip_count.csv")
    merged = target.merge(
        context,
        left_on="context_row_id",
        right_on="row_id",
        how="left",
        validate="one_to_one",
        suffixes=("_target", "_context"),
    )
    if len(merged) != expected_rows:
        raise ValueError(f"Expected {expected_rows} TRAIN count rows, got {len(merged)}")
    if int(merged["row_id"].isna().sum()) != 0:
        raise ValueError("Every TRAIN trip_count row must resolve to person_day_context")
    k = merged["target_trip_count"].astype(np.int64).to_numpy()
    y = merged["target_excess_count"].astype(np.int64).to_numpy()
    if not np.array_equal(y, k - 1):
        raise ValueError("COUNT_A target must satisfy Y=K-1 exactly")
    if int(k.min()) != expected_k_min or int(k.max()) != expected_k_max:
        raise ValueError(
            f"TRAIN count support mismatch: observed {int(k.min())}..{int(k.max())}; "
            f"expected {expected_k_min}..{expected_k_max}"
        )
    w_target = merged["fit_weight_P_GEW_target"].astype(float).to_numpy()
    w_context = merged["fit_weight_P_GEW_context"].astype(float).to_numpy()
    if not np.allclose(w_target, w_context, rtol=0.0, atol=1e-12):
        raise ValueError("P_GEW mismatch between trip_count and context tables")
    if not np.isfinite(w_target).all() or np.any(w_target <= 0):
        raise ValueError("All count fitting weights must be finite and strictly positive")
    encoder = build_count_a_encoder_manifest(merged, feature_columns)
    x, unseen = transform_count_context(merged, encoder)
    if any(unseen.values()):
        raise ValueError("TRAIN count encoder generated unseen categories from TRAIN")
    return (
        EncodedCountData(
            x=x,
            y=y.astype(np.float64),
            k=k,
            w=w_target,
            source_rows=len(merged),
            feature_names=list(encoder["feature_names"]),
            categories=dict(encoder["categories"]),
            reference_categories=dict(encoder["reference_categories"]),
            merged=merged,
            k_min=expected_k_min,
            k_max=expected_k_max,
        ),
        encoder,
    )


def feature_matrix_sha256(data: EncodedCountData) -> str:
    h = hashlib.sha256()
    h.update(str(data.x.shape).encode())
    h.update(np.ascontiguousarray(data.x, dtype=np.float64).tobytes())
    h.update(np.ascontiguousarray(data.y, dtype=np.float64).tobytes())
    h.update(np.ascontiguousarray(data.w, dtype=np.float64).tobytes())
    h.update("\n".join(data.feature_names).encode())
    return h.hexdigest()


def count_support(k_min: int, k_max: int) -> np.ndarray:
    return np.arange(k_min, k_max + 1, dtype=np.int64)


def canonical_count_keys(k_min: int, k_max: int) -> list[str]:
    return [f"K:{int(k):06d}" for k in count_support(k_min, k_max)]


def weighted_empirical_pmf(
    k: np.ndarray,
    w: np.ndarray,
    k_min: int,
    k_max: int,
) -> np.ndarray:
    support = count_support(k_min, k_max)
    mass = np.zeros(len(support), dtype=np.float64)
    for value, weight in zip(np.asarray(k, dtype=np.int64), np.asarray(w, dtype=float), strict=True):
        if value < k_min or value > k_max:
            raise ValueError(f"Count outside frozen support: {value}")
        mass[value - k_min] += weight
    total = float(mass.sum())
    if not math.isfinite(total) or total <= 0:
        raise ValueError("Weighted empirical PMF has no positive finite mass")
    pmf = mass / total
    assert_pmf(pmf)
    return pmf


def assert_pmf(pmf: np.ndarray, atol: float = 1e-12) -> None:
    array = np.asarray(pmf, dtype=float)
    if array.ndim not in (1, 2):
        raise ValueError("PMF must be one- or two-dimensional")
    if not np.isfinite(array).all() or np.any(array < -atol):
        raise ValueError("PMF contains invalid probabilities")
    sums = array.sum(axis=-1)
    if not np.allclose(sums, 1.0, rtol=0.0, atol=atol):
        raise ValueError("PMF rows do not sum to one")


def weighted_discrete_crps(
    observed_k: np.ndarray,
    pmf: np.ndarray,
    w: np.ndarray,
    k_min: int,
) -> float:
    probs = np.asarray(pmf, dtype=float)
    if probs.ndim == 1:
        probs = np.repeat(probs[np.newaxis, :], len(observed_k), axis=0)
    assert_pmf(probs)
    if probs.shape[0] != len(observed_k):
        raise ValueError("PMF row count does not match outcomes")
    cdf = np.cumsum(probs, axis=1)
    support = np.arange(k_min, k_min + probs.shape[1], dtype=np.int64)
    step = (support[np.newaxis, :] >= np.asarray(observed_k, dtype=np.int64)[:, np.newaxis]).astype(float)
    row_crps = np.sum((cdf - step) ** 2, axis=1)
    return float(np.average(row_crps, weights=np.asarray(w, dtype=float)))


def training_metrics_from_pmfs(
    data: EncodedCountData,
    pmfs: np.ndarray,
) -> dict[str, float]:
    probs = np.asarray(pmfs, dtype=float)
    if probs.ndim == 1:
        probs = np.repeat(probs[np.newaxis, :], data.source_rows, axis=0)
    assert_pmf(probs)
    support = count_support(data.k_min, data.k_max).astype(float)
    expected_k = probs @ support
    observed_mean = float(np.average(data.k.astype(float), weights=data.w))
    predicted_mean = float(np.average(expected_k, weights=data.w))
    tail_threshold = min(10, data.k_max)
    observed_tail = float(np.average((data.k >= tail_threshold).astype(float), weights=data.w))
    predicted_tail = float(
        np.average(
            probs[:, (support >= tail_threshold)].sum(axis=1),
            weights=data.w,
        )
    )
    return {
        "weighted_discrete_crps_on_k": weighted_discrete_crps(
            data.k, probs, data.w, data.k_min
        ),
        "weighted_observed_mean_k": observed_mean,
        "weighted_predicted_mean_k": predicted_mean,
        "weighted_observed_p_k_ge_10": observed_tail,
        "weighted_predicted_p_k_ge_10": predicted_tail,
    }


def fit_reference(data: EncodedCountData) -> tuple[dict[str, Any], np.ndarray]:
    pmf = weighted_empirical_pmf(data.k, data.w, data.k_min, data.k_max)
    model = {
        "model_type": "WEIGHTED_UNCONDITIONAL_POSITIVE_COUNT_PMF_V1",
        "support_k": count_support(data.k_min, data.k_max).tolist(),
        "support_keys": canonical_count_keys(data.k_min, data.k_max),
        "probabilities": pmf.tolist(),
        "train_rows": data.source_rows,
        "weighting": "P_GEW",
    }
    return model, pmf


def _nb2_logpmf(y: np.ndarray, mu: np.ndarray, alpha: float) -> np.ndarray:
    if not math.isfinite(alpha) or alpha <= 0:
        raise ValueError("NB2 alpha must be finite and positive")
    r = 1.0 / alpha
    return (
        gammaln(y + r)
        - gammaln(r)
        - gammaln(y + 1.0)
        + r * (math.log(r) - np.log(r + mu))
        + y * (np.log(mu) - np.log(r + mu))
    )


def _weighted_mom_alpha(y: np.ndarray, w: np.ndarray) -> float:
    mean = float(np.average(y, weights=w))
    variance = float(np.average((y - mean) ** 2, weights=w))
    if mean <= 0:
        return 0.1
    raw = (variance - mean) / (mean * mean)
    return max(float(raw), 0.1)


def nb2_truncated_pmf_matrix(
    mu: np.ndarray,
    alpha: float,
    k_min: int,
    k_max: int,
) -> np.ndarray:
    if k_min != 1:
        raise ValueError("F3.2d COUNT_A expects positive K support starting at 1")
    y_support = np.arange(0, k_max, dtype=np.float64)
    mu_array = np.asarray(mu, dtype=float)
    rows: list[np.ndarray] = []
    for value in mu_array:
        logp = _nb2_logpmf(y_support, np.full_like(y_support, value), alpha)
        normalized = np.exp(logp - logsumexp(logp))
        rows.append(normalized)
    pmf = np.vstack(rows)
    assert_pmf(pmf)
    return pmf


def fit_nb2_l2(
    data: EncodedCountData,
    lambda_l2: float,
    maxiter: int,
    ftol: float,
    gtol: float,
    coefficient_bounds: tuple[float, float],
    log_alpha_bounds: tuple[float, float],
    reject_if_boundary_hit: bool,
) -> tuple[dict[str, Any], np.ndarray]:
    if lambda_l2 < 0:
        raise ValueError("lambda_l2 must be non-negative")
    n_features = data.x.shape[1]
    weight_sum = float(data.w.sum())
    mean_y = float(np.average(data.y, weights=data.w))
    intercept_start = math.log(max(mean_y, 1e-6))
    alpha_start = _weighted_mom_alpha(data.y, data.w)
    log_alpha_start = float(np.clip(math.log(alpha_start), *log_alpha_bounds))

    def objective(theta: np.ndarray) -> tuple[float, np.ndarray]:
        intercept = float(theta[0])
        beta = theta[1 : n_features + 1]
        log_alpha = float(theta[-1])
        alpha = math.exp(log_alpha)
        eta = intercept + data.x @ beta
        mu = np.exp(eta)
        if not np.isfinite(mu).all():
            return 1e100, np.zeros_like(theta)
        logp = _nb2_logpmf(data.y, mu, alpha)
        weighted_nll = -float(np.sum(data.w * logp) / weight_sum)
        penalty = 0.5 * lambda_l2 * float(beta @ beta)

        residual_eta = (mu - data.y) / (1.0 + alpha * mu)
        weighted_residual = data.w * residual_eta / weight_sum
        grad = np.empty_like(theta)
        grad[0] = float(weighted_residual.sum())
        grad[1 : n_features + 1] = data.x.T @ weighted_residual + lambda_l2 * beta

        r = 1.0 / alpha
        dlogp_dr = (
            digamma(data.y + r)
            - digamma(r)
            + math.log(r)
            + 1.0
            - np.log(r + mu)
            - (r + data.y) / (r + mu)
        )
        grad[-1] = float(np.sum(data.w * (r * dlogp_dr)) / weight_sum)
        return weighted_nll + penalty, grad

    start = np.concatenate(
        [
            np.asarray([intercept_start], dtype=np.float64),
            np.zeros(n_features, dtype=np.float64),
            np.asarray([log_alpha_start], dtype=np.float64),
        ]
    )
    coef_lo, coef_hi = coefficient_bounds
    alpha_lo, alpha_hi = log_alpha_bounds
    bounds = [(coef_lo, coef_hi)] * (n_features + 1) + [(alpha_lo, alpha_hi)]
    result = minimize(
        fun=lambda theta: objective(theta)[0],
        x0=start,
        jac=lambda theta: objective(theta)[1],
        method="L-BFGS-B",
        bounds=bounds,
        options={"maxiter": maxiter, "ftol": ftol, "gtol": gtol, "maxls": 50},
    )
    if not result.success:
        raise RuntimeError(f"COUNT_A optimizer failed: {result.message}")

    tolerance = 1e-6
    boundary_hit = any(
        abs(float(value) - lo) <= tolerance or abs(float(value) - hi) <= tolerance
        for value, (lo, hi) in zip(result.x, bounds, strict=True)
    )
    if boundary_hit and reject_if_boundary_hit:
        raise RuntimeError("COUNT_A optimizer solution hit a frozen numerical bound")

    intercept = float(result.x[0])
    beta = result.x[1 : n_features + 1].astype(np.float64)
    log_alpha = float(result.x[-1])
    alpha = math.exp(log_alpha)
    mu = np.exp(intercept + data.x @ beta)
    pmfs = nb2_truncated_pmf_matrix(mu, alpha, data.k_min, data.k_max)
    untruncated_nll = -float(np.average(_nb2_logpmf(data.y, mu, alpha), weights=data.w))
    model = {
        "model_type": "WEIGHTED_NB2_GLM_ON_EXCESS_COUNT_L2_V1",
        "target": "Y=K-1",
        "link": "LOG",
        "variance": "MU + ALPHA*MU^2",
        "objective": "weighted_mean_nb2_nll + 0.5*lambda_l2*||beta||^2",
        "lambda_l2": float(lambda_l2),
        "intercept_penalized": False,
        "dispersion_penalized": False,
        "intercept": intercept,
        "coefficients": beta.tolist(),
        "feature_names": data.feature_names,
        "alpha": alpha,
        "log_alpha": log_alpha,
        "dispersion_source": "TRAIN_MLE",
        "tail_policy": "TRUNCATE_AND_RENORMALIZE_TO_K_1_THROUGH_K_MAX_TRAIN",
        "k_min": data.k_min,
        "k_max_train": data.k_max,
        "posthoc_clip": False,
        "train_untruncated_weighted_nb2_nll": untruncated_nll,
        "optimizer": {
            "method": "L-BFGS-B",
            "success": bool(result.success),
            "message": str(result.message),
            "nit": int(result.nit),
            "objective_value": float(result.fun),
            "coefficient_bounds": [float(coef_lo), float(coef_hi)],
            "log_alpha_bounds": [float(alpha_lo), float(alpha_hi)],
            "boundary_hit": bool(boundary_hit),
            "start_alpha": float(alpha_start),
            "start_intercept": float(intercept_start),
        },
    }
    return model, pmfs


def _normalized_key(values: tuple[Any, ...]) -> tuple[str, ...]:
    return tuple(_as_category(value) for value in values)


def _cell_id(level: int, key: tuple[str, ...]) -> str:
    payload = json.dumps([level, *key], separators=(",", ":"), ensure_ascii=False).encode()
    return hashlib.sha256(payload).hexdigest()[:16]


def build_count_backoff_model(
    merged: pd.DataFrame,
    hierarchy: list[list[str]],
    weight_column: str,
    target_column: str,
    k_min: int,
    k_max: int,
    direct_support_min_n: int,
) -> tuple[dict[str, Any], np.ndarray, pd.DataFrame]:
    if hierarchy[-1] != [GLOBAL_TOKEN]:
        raise ValueError("COUNT_BACKOFF_V1 must terminate in GLOBAL")
    support = count_support(k_min, k_max)
    support_keys = canonical_count_keys(k_min, k_max)
    model_levels: list[dict[str, Any]] = []
    lookup_levels: list[dict[tuple[str, ...], tuple[int, np.ndarray]]] = []
    summary_rows: list[dict[str, Any]] = []

    for level_number, dimensions in enumerate(hierarchy, start=1):
        cells: list[dict[str, Any]] = []
        lookup: dict[tuple[str, ...], tuple[int, np.ndarray]] = {}
        if dimensions == [GLOBAL_TOKEN]:
            groups = [((), merged)]
        else:
            groups = []
            grouper: str | list[str]
            if len(dimensions) == 1:
                grouper = dimensions[0]
            else:
                grouper = dimensions
            for raw_key, frame in merged.groupby(grouper, dropna=False, sort=True):
                key_tuple = raw_key if isinstance(raw_key, tuple) else (raw_key,)
                groups.append((_normalized_key(key_tuple), frame))

        eligible_count = 0
        for key, frame in groups:
            source_n = int(len(frame))
            pmf = weighted_empirical_pmf(
                frame[target_column].to_numpy(dtype=np.int64),
                frame[weight_column].to_numpy(dtype=float),
                k_min,
                k_max,
            )
            eligible = dimensions == [GLOBAL_TOKEN] or source_n >= direct_support_min_n
            eligible_count += int(eligible)
            lookup[key] = (source_n, pmf)
            cells.append(
                {
                    "cell_id": _cell_id(level_number, key),
                    "key": list(key),
                    "source_n": source_n,
                    "low_n": bool(source_n < direct_support_min_n),
                    "eligible_direct": bool(eligible),
                    "probabilities": pmf.tolist(),
                }
            )
        cells.sort(key=lambda cell: tuple(cell["key"]))
        model_levels.append(
            {
                "level": level_number,
                "dimensions": dimensions,
                "cells": cells,
            }
        )
        lookup_levels.append(lookup)
        summary_rows.append(
            {
                "level": level_number,
                "dimensions": "+".join(dimensions),
                "cells_total": len(cells),
                "cells_eligible_direct": eligible_count,
                "cells_low_n": len(cells) - eligible_count if dimensions != [GLOBAL_TOKEN] else 0,
                "train_rows_selected": 0,
            }
        )

    selected_pmfs: list[np.ndarray] = []
    selected_levels: list[int] = []
    for _, row in merged.iterrows():
        selected: tuple[int, np.ndarray] | None = None
        for level_number, dimensions in enumerate(hierarchy, start=1):
            if dimensions == [GLOBAL_TOKEN]:
                key = ()
            else:
                key = tuple(_as_category(row[column]) for column in dimensions)
            source_n, pmf = lookup_levels[level_number - 1][key]
            if dimensions == [GLOBAL_TOKEN] or source_n >= direct_support_min_n:
                selected = (level_number, pmf)
                break
        if selected is None:
            raise RuntimeError("COUNT_BACKOFF_V1 failed to resolve a TRAIN row")
        selected_levels.append(selected[0])
        selected_pmfs.append(selected[1])

    for level_number in selected_levels:
        summary_rows[level_number - 1]["train_rows_selected"] += 1

    pmfs = np.vstack(selected_pmfs)
    assert_pmf(pmfs)
    model = {
        "model_type": "WEIGHTED_CONDITIONAL_EMPIRICAL_POSITIVE_COUNT_PMF_WITH_BACKOFF_V1",
        "hierarchy_id": "COUNT_BACKOFF_V1",
        "fit_partition": "TRAIN",
        "support_count_basis": "RAW_STRICT_TRAIN_ROWS_BEFORE_WEIGHTING",
        "direct_support_min_n": direct_support_min_n,
        "low_n_rule": f"source_n < {direct_support_min_n}",
        "probability_weight": "P_GEW",
        "smoothing": "NONE",
        "support_k": support.tolist(),
        "support_keys": support_keys,
        "support_order": "CANONICAL_LEXICAL_KEY",
        "levels": model_levels,
    }
    return model, pmfs, pd.DataFrame(summary_rows)


def finite_metrics(metrics: dict[str, float]) -> bool:
    return all(math.isfinite(float(value)) for value in metrics.values())
