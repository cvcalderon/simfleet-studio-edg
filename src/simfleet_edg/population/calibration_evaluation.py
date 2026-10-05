"""I/O-free F1 population CAL evaluation primitives.

This module accepts already-materialized DataFrames. It deliberately performs no file I/O
and therefore cannot itself open CAL or TEST sources.
"""
from __future__ import annotations

import hashlib
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass

import numpy as np
import pandas as pd

LOW_N_THRESHOLD = 30
BOOTSTRAP_REPLICATES = 1000
BOOTSTRAP_MASTER_SEED = 20261005


@dataclass(frozen=True)
class FamilyResult:
    family_id: str
    error: float
    decision_cells: int
    low_n_cells: int


def _stable_seed(master_seed: int, *parts: str) -> int:
    payload = "|".join([str(master_seed), *map(str, parts)]).encode()
    return int.from_bytes(hashlib.sha256(payload).digest()[:8], "big", signed=False)


def stock_category(value: float | int, *, cap: int) -> str:
    value_i = int(value)
    if value_i < 0:
        raise ValueError("Stock quantity cannot be negative")
    if cap == 3:
        return {0: "ZERO", 1: "ONE", 2: "TWO"}.get(value_i, "THREE_PLUS")
    if cap == 10:
        if value_i == 0:
            return "ZERO"
        if value_i == 1:
            return "ONE"
        if value_i >= 10:
            return "TEN_PLUS"
        return "TWO_TO_NINE"
    raise ValueError(f"Unsupported stock cap: {cap}")


def weighted_distribution(
    frame: pd.DataFrame,
    *,
    outcome: str,
    weight: str,
    categories: Sequence[str] | None = None,
) -> dict[str, float]:
    if frame.empty:
        return {}
    weights = frame[weight].astype(float).to_numpy()
    if np.any(~np.isfinite(weights)) or np.any(weights < 0) or float(weights.sum()) <= 0:
        raise ValueError("Weights must be finite, non-negative and have positive total")
    values = frame[outcome].astype(str)
    grouped = pd.Series(weights).groupby(values.reset_index(drop=True)).sum()
    if categories is None:
        cats = sorted(str(v) for v in grouped.index)
    else:
        cats = [str(v) for v in categories]
    total = float(grouped.sum())
    return {cat: float(grouped.get(cat, 0.0)) / total for cat in cats}


def tvd(a: Mapping[str, float], b: Mapping[str, float]) -> float:
    categories = sorted(set(a) | set(b))
    return 0.5 * sum(abs(float(a.get(k, 0.0)) - float(b.get(k, 0.0))) for k in categories)


def conditional_tvd_family(
    reference: pd.DataFrame,
    synthetic: pd.DataFrame,
    *,
    family_id: str,
    condition_cols: Sequence[str],
    outcome_col: str,
    reference_weight_col: str,
    synthetic_weight_col: str,
    low_n_threshold: int = LOW_N_THRESHOLD,
    categories: Sequence[str] | None = None,
) -> FamilyResult:
    if reference.empty:
        raise ValueError(f"{family_id}: empty empirical reference")
    ref = reference.copy()
    syn = synthetic.copy()
    keys = list(condition_cols)
    decision: list[tuple[float, float]] = []
    low_n = 0
    for key, ref_group in ref.groupby(keys, dropna=False, sort=True):
        key_tuple = key if isinstance(key, tuple) else (key,)
        mask = pd.Series(True, index=syn.index)
        for col, value in zip(keys, key_tuple, strict=True):
            mask &= syn[col].eq(value)
        syn_group = syn.loc[mask]
        if len(ref_group) < low_n_threshold:
            low_n += 1
            continue
        if syn_group.empty:
            cell_error = 1.0
        else:
            ref_dist = weighted_distribution(
                ref_group,
                outcome=outcome_col,
                weight=reference_weight_col,
                categories=categories,
            )
            syn_dist = weighted_distribution(
                syn_group,
                outcome=outcome_col,
                weight=synthetic_weight_col,
                categories=categories,
            )
            cell_error = tvd(ref_dist, syn_dist)
        ref_mass = float(ref_group[reference_weight_col].astype(float).sum())
        decision.append((ref_mass, cell_error))
    if not decision:
        raise ValueError(f"{family_id}: no support-OK decision cells")
    total_mass = sum(mass for mass, _ in decision)
    error = sum(mass * value for mass, value in decision) / total_mass
    return FamilyResult(family_id, float(error), len(decision), low_n)


def bike_ebike_family_error(bike: FamilyResult, ebike: FamilyResult) -> FamilyResult:
    return FamilyResult(
        "HH_BIKE_EBIKE_STOCK_BY_SIZE",
        max(bike.error, ebike.error),
        min(bike.decision_cells, ebike.decision_cells),
        max(bike.low_n_cells, ebike.low_n_cells),
    )


def bootstrap_materiality_threshold(
    household_ids: Sequence[str],
    baseline_error_fn: Callable[[list[str]], float],
    *,
    family_id: str,
    baseline_error: float,
    replicates: int = BOOTSTRAP_REPLICATES,
    master_seed: int = BOOTSTRAP_MASTER_SEED,
) -> float:
    ids = np.asarray([str(value) for value in household_ids], dtype=object)
    if len(ids) == 0:
        raise ValueError("Cannot bootstrap zero households")
    rng = np.random.default_rng(_stable_seed(master_seed, "F1_PCONSTR_CAL_MATERIALITY_V1", family_id))
    deviations = np.empty(replicates, dtype=float)
    for b in range(replicates):
        sampled = rng.choice(ids, size=len(ids), replace=True).tolist()
        deviations[b] = abs(float(baseline_error_fn(sampled)) - float(baseline_error))
    return float(np.quantile(deviations, 0.95, method="higher"))


def select_constrained_variant(
    errors_u: Mapping[str, float],
    errors_w: Mapping[str, float],
    thresholds: Mapping[str, float],
) -> str:
    families = sorted(thresholds)
    if set(errors_u) != set(families) or set(errors_w) != set(families):
        raise ValueError("HD_U/HD_W error families must exactly match thresholds")
    materially_better = any(errors_u[f] - errors_w[f] > thresholds[f] for f in families)
    nondegrading = all(errors_w[f] - errors_u[f] <= thresholds[f] for f in families)
    return "P_CONSTR_RMIN_V2_HD_W" if materially_better and nondegrading else "P_CONSTR_RMIN_V2_HD_U"


def select_final_candidate(
    constrained_id: str,
    constrained_errors: Mapping[str, float],
    ptrs_errors: Mapping[str, float],
    thresholds: Mapping[str, float],
    *,
    constrained_fit_l1: int,
    constrained_fit_max_abs: int,
    ptrs_fit_l1: int,
    ptrs_fit_max_abs: int,
    engineering_gate_pass: bool,
) -> str:
    families = sorted(thresholds)
    if set(constrained_errors) != set(families) or set(ptrs_errors) != set(families):
        raise ValueError("Candidate error families must exactly match thresholds")
    fit_dominance = (
        int(constrained_fit_l1) < int(ptrs_fit_l1)
        and int(constrained_fit_max_abs) <= int(ptrs_fit_max_abs)
    )
    nondegrading = all(
        constrained_errors[f] - ptrs_errors[f] <= thresholds[f] for f in families
    )
    if fit_dominance and nondegrading and engineering_gate_pass:
        return constrained_id
    return "P_TRS_V1_FINAL"
