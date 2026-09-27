"""Metric primitives frozen for F3.3 CAL evaluation."""

from __future__ import annotations

from collections.abc import Iterable

import numpy as np
import pandas as pd


def _arrays(values: Iterable[float], weights: Iterable[float]) -> tuple[np.ndarray, np.ndarray]:
    v = np.asarray(list(values), dtype=float)
    w = np.asarray(list(weights), dtype=float)
    if v.shape != w.shape:
        raise ValueError("values/weights shape mismatch")
    mask = np.isfinite(v) & np.isfinite(w) & (w > 0)
    if not mask.any():
        raise ValueError("no finite positive-weight observations")
    return v[mask], w[mask]


def weighted_mean(values: Iterable[float], weights: Iterable[float]) -> float:
    v, w = _arrays(values, weights)
    return float(np.average(v, weights=w))


def weighted_distribution(categories: Iterable[object], weights: Iterable[float]) -> pd.Series:
    frame = pd.DataFrame({"category": pd.Series(list(categories), dtype="string"), "weight": list(weights)})
    frame["weight"] = pd.to_numeric(frame["weight"], errors="raise")
    if (frame["weight"] < 0).any() or not np.isfinite(frame["weight"]).all():
        raise ValueError("weights must be finite and non-negative")
    out = frame.groupby("category", sort=True, dropna=False)["weight"].sum()
    if float(out.sum()) <= 0:
        raise ValueError("total weight must be positive")
    return out / out.sum()


def total_variation_distance(left: pd.Series, right: pd.Series) -> float:
    idx = left.index.union(right.index)
    left_aligned = left.reindex(idx, fill_value=0.0).astype(float)
    right_aligned = right.reindex(idx, fill_value=0.0).astype(float)
    return float(0.5 * np.abs(left_aligned - right_aligned).sum())


def weighted_quantile(values: Iterable[float], weights: Iterable[float], q: float) -> float:
    if not 0 <= q <= 1:
        raise ValueError("q must be in [0,1]")
    v, w = _arrays(values, weights)
    order = np.argsort(v, kind="mergesort")
    v, w = v[order], w[order]
    cumulative = np.cumsum(w)
    cutoff = q * cumulative[-1]
    return float(v[np.searchsorted(cumulative, cutoff, side="left")])


def wasserstein_1d(
    values_a: Iterable[float],
    weights_a: Iterable[float],
    values_b: Iterable[float],
    weights_b: Iterable[float],
) -> float:
    a, wa = _arrays(values_a, weights_a)
    b, wb = _arrays(values_b, weights_b)
    oa = np.argsort(a, kind="mergesort")
    ob = np.argsort(b, kind="mergesort")
    a, wa = a[oa], wa[oa]
    b, wb = b[ob], wb[ob]
    wa = wa / wa.sum()
    wb = wb / wb.sum()
    support = np.sort(np.unique(np.concatenate((a, b))))
    if len(support) < 2:
        return 0.0
    lower = support[:-1]
    widths = np.diff(support)
    ca = np.cumsum(wa)
    cb = np.cumsum(wb)
    ia = np.searchsorted(a, lower, side="right") - 1
    ib = np.searchsorted(b, lower, side="right") - 1
    fa = np.where(ia >= 0, ca[np.maximum(ia, 0)], 0.0)
    fb = np.where(ib >= 0, cb[np.maximum(ib, 0)], 0.0)
    return float(np.sum(np.abs(fa - fb) * widths))


def weighted_bernoulli_logloss(
    observed: Iterable[int], probability: Iterable[float], weights: Iterable[float]
) -> float:
    y = np.asarray(list(observed), dtype=float)
    p = np.asarray(list(probability), dtype=float)
    w = np.asarray(list(weights), dtype=float)
    if not (y.shape == p.shape == w.shape):
        raise ValueError("input shapes differ")
    if not np.isin(y, [0.0, 1.0]).all():
        raise ValueError("Bernoulli outcomes must be 0/1")
    if not np.isfinite(p).all() or ((p < 0) | (p > 1)).any():
        raise ValueError("probabilities outside [0,1]")
    eps = np.finfo(float).eps
    pc = np.clip(p, eps, 1.0 - eps)
    loss = -(y * np.log(pc) + (1 - y) * np.log1p(-pc))
    return float(np.average(loss, weights=w))


def weighted_categorical_logloss(
    observed_index: Iterable[int], probabilities: np.ndarray, weights: Iterable[float]
) -> float:
    y = np.asarray(list(observed_index), dtype=int)
    probs = np.asarray(probabilities, dtype=float)
    w = np.asarray(list(weights), dtype=float)
    if probs.ndim != 2 or probs.shape[0] != len(y) or len(w) != len(y):
        raise ValueError("categorical probability shape mismatch")
    if not np.isfinite(probs).all() or (probs < 0).any():
        raise ValueError("invalid categorical probabilities")
    if not np.allclose(probs.sum(axis=1), 1.0, atol=1e-10):
        raise ValueError("categorical probabilities must sum to 1")
    if (y < 0).any() or (y >= probs.shape[1]).any():
        raise ValueError("observed class index out of support")
    p = np.clip(probs[np.arange(len(y)), y], np.finfo(float).tiny, 1.0)
    return float(np.average(-np.log(p), weights=w))


def weighted_discrete_crps(
    observed_k: Iterable[int], pmf: np.ndarray, weights: Iterable[float], k_min: int
) -> float:
    y = np.asarray(list(observed_k), dtype=np.int64)
    probs = np.asarray(pmf, dtype=float)
    w = np.asarray(list(weights), dtype=float)
    if probs.ndim == 1:
        probs = np.repeat(probs[np.newaxis, :], len(y), axis=0)
    if probs.shape[0] != len(y) or len(w) != len(y):
        raise ValueError("CRPS row mismatch")
    if not np.isfinite(probs).all() or (probs < 0).any():
        raise ValueError("invalid PMF")
    if not np.allclose(probs.sum(axis=1), 1.0, atol=1e-10):
        raise ValueError("PMF rows must sum to 1")
    cdf = np.cumsum(probs, axis=1)
    support = np.arange(k_min, k_min + probs.shape[1], dtype=np.int64)
    step = (support[np.newaxis, :] >= y[:, np.newaxis]).astype(float)
    row_crps = np.sum((cdf - step) ** 2, axis=1)
    return float(np.average(row_crps, weights=w))


def departure_hour(clock_minute: Iterable[float]) -> pd.Series:
    minute = pd.to_numeric(pd.Series(list(clock_minute)), errors="raise")
    if ((minute < 0) | (minute >= 1440)).any():
        raise ValueError("departure clock must be in [0,1440)")
    return (minute // 60).astype(int).astype(str)


def trip_count_category(values: Iterable[int]) -> pd.Series:
    numeric = pd.to_numeric(pd.Series(list(values)), errors="raise")
    if (numeric < 0).any():
        raise ValueError("trip counts cannot be negative")
    return numeric.map(lambda x: "12_PLUS" if x >= 12 else str(int(x)))
