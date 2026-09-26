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
from scipy.optimize import minimize
from scipy.special import expit

RESERVED_UNSEEN = "__UNSEEN__"
RESERVED_MISSING = "__MISSING_CONTEXT__"


@dataclass(frozen=True)
class EncodedParticipationData:
    x: np.ndarray
    y: np.ndarray
    w: np.ndarray
    feature_names: list[str]
    categories: dict[str, list[str]]
    source_rows: int
    weighted_observed_share: float


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


def _train_categories(series: pd.Series) -> list[str]:
    observed = sorted({_as_category(v) for v in series.tolist()})
    for token in (RESERVED_MISSING, RESERVED_UNSEEN):
        if token not in observed:
            observed.append(token)
    return observed


def build_encoder_manifest(train_context: pd.DataFrame, feature_columns: list[str]) -> dict[str, Any]:
    categories = {column: _train_categories(train_context[column]) for column in feature_columns}
    feature_names = [f"{column}=={value}" for column in feature_columns for value in categories[column]]
    return {
        "encoder": "DETERMINISTIC_FULL_ONE_HOT_V1",
        "fit_partition": "TRAIN",
        "feature_columns": feature_columns,
        "categories": categories,
        "feature_names": feature_names,
        "unknown_token": RESERVED_UNSEEN,
        "missing_token": RESERVED_MISSING,
        "drop": None,
    }


def transform_context(
    context: pd.DataFrame, encoder_manifest: dict[str, Any]
) -> tuple[np.ndarray, dict[str, int]]:
    feature_columns = encoder_manifest["feature_columns"]
    categories: dict[str, list[str]] = encoder_manifest["categories"]
    blocks: list[np.ndarray] = []
    unseen_counts: dict[str, int] = {}
    for column in feature_columns:
        cat = categories[column]
        index = {value: i for i, value in enumerate(cat)}
        unseen_idx = index[RESERVED_UNSEEN]
        values = [_as_category(v) for v in context[column].tolist()]
        mapped = [v if v in index else RESERVED_UNSEEN for v in values]
        unseen_counts[column] = sum(v == RESERVED_UNSEEN for v in mapped)
        block = np.zeros((len(context), len(cat)), dtype=np.float64)
        rows = np.arange(len(context))
        cols = np.asarray([index.get(v, unseen_idx) for v in mapped], dtype=np.int64)
        block[rows, cols] = 1.0
        blocks.append(block)
    return np.concatenate(blocks, axis=1), unseen_counts


def load_train_participation(
    materialized_root: Path,
    feature_columns: list[str],
    expected_rows: int,
) -> tuple[EncodedParticipationData, dict[str, Any]]:
    context = pd.read_csv(materialized_root / "TRAIN" / "person_day_context.csv")
    target = pd.read_csv(materialized_root / "TRAIN" / "participation.csv")
    merged = target.merge(
        context,
        left_on="context_row_id",
        right_on="row_id",
        how="left",
        validate="one_to_one",
        suffixes=("_target", "_context"),
    )
    if len(merged) != expected_rows:
        raise ValueError(f"Expected {expected_rows} TRAIN participation rows, got {len(merged)}")
    if merged[feature_columns].isna().all(axis=None):
        raise ValueError("All feature values are missing")
    y = merged["target_trip_day"].astype(np.int8).to_numpy()
    if set(np.unique(y)) != {0, 1}:
        raise ValueError("Participation target must be binary with both classes present")
    w_target = merged["fit_weight_P_GEW_target"].astype(float).to_numpy()
    w_context = merged["fit_weight_P_GEW_context"].astype(float).to_numpy()
    if not np.allclose(w_target, w_context, rtol=0.0, atol=1e-12):
        raise ValueError("P_GEW mismatch between participation and context tables")
    if not np.isfinite(w_target).all() or np.any(w_target <= 0):
        raise ValueError("All fitting weights must be finite and strictly positive")
    encoder = build_encoder_manifest(merged, feature_columns)
    x, unseen = transform_context(merged, encoder)
    if any(unseen.values()):
        raise ValueError("TRAIN encoder generated unseen categories from its own fit partition")
    weighted_share = float(np.average(y, weights=w_target))
    data = EncodedParticipationData(
        x=x,
        y=y.astype(np.float64),
        w=w_target,
        feature_names=encoder["feature_names"],
        categories=encoder["categories"],
        source_rows=len(merged),
        weighted_observed_share=weighted_share,
    )
    return data, encoder


def weighted_logloss(y: np.ndarray, p: np.ndarray, w: np.ndarray) -> float:
    clipped = np.clip(np.asarray(p, dtype=float), 1e-15, 1 - 1e-15)
    terms = -(y * np.log(clipped) + (1 - y) * np.log(1 - clipped))
    return float(np.average(terms, weights=w))


def weighted_brier(y: np.ndarray, p: np.ndarray, w: np.ndarray) -> float:
    return float(np.average((np.asarray(p) - y) ** 2, weights=w))


def training_metrics(data: EncodedParticipationData, p: np.ndarray) -> dict[str, float]:
    return {
        "weighted_bernoulli_logloss": weighted_logloss(data.y, p, data.w),
        "weighted_brier": weighted_brier(data.y, p, data.w),
        "weighted_observed_trip_day_share": data.weighted_observed_share,
        "weighted_predicted_trip_day_share": float(np.average(p, weights=data.w)),
    }


def fit_reference(data: EncodedParticipationData) -> tuple[dict[str, Any], np.ndarray]:
    p0 = data.weighted_observed_share
    prediction = np.full(data.source_rows, p0, dtype=np.float64)
    model = {
        "model_type": "WEIGHTED_EMPIRICAL_BERNOULLI_V1",
        "probability_trip_day": p0,
        "train_rows": data.source_rows,
    }
    return model, prediction


def fit_logistic_l2(
    data: EncodedParticipationData,
    lambda_l2: float,
    maxiter: int,
    ftol: float,
    gtol: float,
) -> tuple[dict[str, Any], np.ndarray]:
    n_features = data.x.shape[1]
    weight_sum = float(data.w.sum())

    def objective(theta: np.ndarray) -> tuple[float, np.ndarray]:
        intercept = theta[0]
        beta = theta[1:]
        z = intercept + data.x @ beta
        p = expit(z)
        nll = np.sum(data.w * (np.logaddexp(0.0, z) - data.y * z)) / weight_sum
        penalty = 0.5 * lambda_l2 * float(beta @ beta)
        residual = data.w * (p - data.y) / weight_sum
        grad = np.empty_like(theta)
        grad[0] = residual.sum()
        grad[1:] = data.x.T @ residual + lambda_l2 * beta
        return float(nll + penalty), grad

    start = np.zeros(n_features + 1, dtype=np.float64)
    result = minimize(
        fun=lambda t: objective(t)[0],
        x0=start,
        jac=lambda t: objective(t)[1],
        method="L-BFGS-B",
        options={"maxiter": maxiter, "ftol": ftol, "gtol": gtol, "maxls": 50},
    )
    if not result.success:
        raise RuntimeError(f"PART_A optimizer failed: {result.message}")
    intercept = float(result.x[0])
    beta = result.x[1:].astype(np.float64)
    prediction = expit(intercept + data.x @ beta)
    model = {
        "model_type": "WEIGHTED_LOGISTIC_L2_V1",
        "objective": "weighted_mean_bernoulli_nll + 0.5*lambda_l2*||beta||^2",
        "intercept_penalized": False,
        "lambda_l2": float(lambda_l2),
        "intercept": intercept,
        "coefficients": beta.tolist(),
        "feature_names": data.feature_names,
        "optimizer": {
            "method": "L-BFGS-B",
            "success": bool(result.success),
            "message": str(result.message),
            "nit": int(result.nit),
            "objective_value": float(result.fun),
        },
    }
    return model, prediction


def lightgbm_parameters(common: dict[str, Any], grid: dict[str, Any], seed: int) -> dict[str, Any]:
    return {
        "objective": common["objective"],
        "learning_rate": float(common["learning_rate"]),
        "n_estimators": int(common["n_estimators"]),
        "max_depth": int(grid["max_depth"]),
        "num_leaves": int(grid["num_leaves"]),
        "min_child_samples": int(grid["min_data_in_leaf"]),
        "reg_lambda": float(grid["lambda_l2"]),
        "feature_fraction": float(common["feature_fraction"]),
        "bagging_fraction": float(common["bagging_fraction"]),
        "bagging_freq": int(common["bagging_freq"]),
        "deterministic": bool(common["deterministic"]),
        "force_col_wise": bool(common["force_col_wise"]),
        "n_jobs": int(common["n_jobs"]),
        "random_state": int(seed),
        "verbosity": -1,
    }


def fit_lightgbm(
    data: EncodedParticipationData,
    common: dict[str, Any],
    grid: dict[str, Any],
    seed: int,
) -> tuple[lgb.LGBMClassifier, np.ndarray, dict[str, Any]]:
    params = lightgbm_parameters(common, grid, seed)
    model = lgb.LGBMClassifier(**params)
    frame = pd.DataFrame(data.x, columns=data.feature_names)
    model.fit(frame, data.y.astype(np.int8), sample_weight=data.w)
    prediction = model.predict_proba(frame)[:, 1]
    meta = {
        "model_type": "LIGHTGBM_BINARY_V1",
        "parameters": params,
        "n_features": int(data.x.shape[1]),
        "n_trees": int(model.booster_.num_trees()),
    }
    return model, prediction, meta


def assert_probabilities(p: np.ndarray) -> None:
    if not np.isfinite(p).all():
        raise ValueError("Non-finite predicted probability")
    if np.any(p <= 0.0) or np.any(p >= 1.0):
        # exact 0/1 would make TRAIN logloss unstable and is not expected here
        raise ValueError("Predicted probabilities must lie strictly inside (0,1)")


def encoder_sha256(encoder_manifest: dict[str, Any]) -> str:
    return hashlib.sha256(canonical_json_bytes(encoder_manifest)).hexdigest()


def feature_matrix_sha256(data: EncodedParticipationData) -> str:
    h = hashlib.sha256()
    h.update(np.ascontiguousarray(data.x, dtype="<f8").tobytes())
    h.update(np.ascontiguousarray(data.y, dtype="<f8").tobytes())
    h.update(np.ascontiguousarray(data.w, dtype="<f8").tobytes())
    return h.hexdigest()


def finite_metrics(metrics: dict[str, float]) -> bool:
    return all(math.isfinite(float(v)) for v in metrics.values())
