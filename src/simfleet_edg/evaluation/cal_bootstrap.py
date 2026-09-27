"""Paired household bootstrap primitives frozen before CAL inspection."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class BootstrapInterval:
    lower: float
    median: float
    upper: float
    confidence_level: float
    replicates: int


def household_bootstrap_multipliers(
    household_ids: Iterable[object],
    *,
    replicates: int,
    seed: int,
) -> np.ndarray:
    """Return integer row multipliers for paired household resampling."""
    ids = np.asarray([str(x) for x in household_ids], dtype=object)
    if ids.ndim != 1 or len(ids) == 0:
        raise ValueError("household_ids must be a non-empty vector")
    unique = np.array(sorted(set(ids.tolist())), dtype=object)
    if len(unique) == 0:
        raise ValueError("no households")
    index = {h: i for i, h in enumerate(unique)}
    row_household_index = np.array([index[x] for x in ids], dtype=np.int64)
    rng = np.random.default_rng(seed)
    out = np.empty((replicates, len(ids)), dtype=np.int32)
    h = len(unique)
    for r in range(replicates):
        draws = rng.integers(0, h, size=h)
        counts = np.bincount(draws, minlength=h).astype(np.int32)
        out[r] = counts[row_household_index]
    return out


def percentile_interval(
    values: Iterable[float], *, confidence_level: float = 0.95
) -> BootstrapInterval:
    arr = np.asarray(list(values), dtype=float)
    arr = arr[np.isfinite(arr)]
    if len(arr) == 0:
        raise ValueError("no finite bootstrap values")
    if not 0 < confidence_level < 1:
        raise ValueError("confidence_level must be in (0,1)")
    alpha = 1.0 - confidence_level
    lo, med, hi = np.quantile(arr, [alpha / 2.0, 0.5, 1.0 - alpha / 2.0])
    return BootstrapInterval(
        lower=float(lo),
        median=float(med),
        upper=float(hi),
        confidence_level=confidence_level,
        replicates=len(arr),
    )
