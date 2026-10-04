"""Exact deterministic scale projection for frozen F1 private-household controls."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

import numpy as np
import pandas as pd

from simfleet_edg.population.age_projection import AGE_ZENSUS_11_SOURCE_CODES
from simfleet_edg.population.zensus_controls import HH_SIZE_CODES, SEX_CODES

SCALE_TARGETS: Final[dict[str, int]] = {"S": 10_000, "M": 100_000, "L": 1_000_000}
EXACT_HOUSEHOLD_SIZES: Final[dict[str, int]] = {
    "PERSON01": 1,
    "PERSON02": 2,
    "PERSON03": 3,
    "PERSON04": 4,
    "PERSON05": 5,
}
ALGORITHM_ID: Final[str] = "EXACT_L1_MODULAR_ROUNDING_V1"
TIE_BREAK_ID: Final[str] = "CANONICAL_WEIGHTED_INCREMENT_V1"


@dataclass(frozen=True)
class ScaleProjectionAudit:
    scale_id: str
    target_persons: int
    reference_persons: int
    bezirk_count: int
    detail_cells: int
    l1_scaled_numerator: int
    structural_zero_violations: int
    divisibility_violations_sizes_1_to_5: int
    all_bezirk_targets_exact: bool


def _canonical_sort(frame: pd.DataFrame) -> pd.DataFrame:
    age_rank = {value: index for index, value in enumerate(AGE_ZENSUS_11_SOURCE_CODES)}
    sex_rank = {value: index for index, value in enumerate(SEX_CODES)}
    hh_rank = {value: index for index, value in enumerate(HH_SIZE_CODES)}
    out = frame.copy()
    out["_age_rank"] = out["age_zensus_11_source_code"].map(age_rank)
    out["_sex_rank"] = out["sex_code"].map(sex_rank)
    out["_hh_rank"] = out["household_size_code"].map(hh_rank)
    if out[["_age_rank", "_sex_rank", "_hh_rank"]].isna().any().any():
        raise ValueError("Cube contains unsupported age/sex/household-size codes")
    return (
        out.sort_values(["bezirk_code", "_age_rank", "_sex_rank", "_hh_rank"])
        .drop(columns=["_age_rank", "_sex_rank", "_hh_rank"])
        .reset_index(drop=True)
    )


def largest_remainder_integerization(
    weights: np.ndarray, total: int, keys: list[str]
) -> np.ndarray:
    """Hamilton integerization using exact integer arithmetic and canonical key ties."""
    values = np.asarray(weights, dtype=np.int64)
    if total < 0 or np.any(values < 0) or int(values.sum()) <= 0:
        raise ValueError("weights and total must define a nonnegative positive-mass allocation")
    if len(values) != len(keys):
        raise ValueError("keys length mismatch")
    denominator = int(values.sum())
    numerators = values * int(total)
    result = numerators // denominator
    remainder_count = int(total - int(result.sum()))
    remainders = numerators % denominator
    order = sorted(
        range(len(values)),
        key=lambda index: (-int(remainders[index]), str(keys[index])),
    )
    for index in order[:remainder_count]:
        result[index] += 1
    return result.astype(int)


def _project_one_bezirk(
    frame: pd.DataFrame,
    *,
    target_persons: int,
    scale_target: int,
    reference_persons: int,
) -> tuple[np.ndarray, int]:
    full = frame["fit_target_value"].to_numpy(dtype=np.int64)
    quota_numerators = full * np.int64(scale_target)
    floors = (quota_numerators // reference_persons).astype(int)
    remainders = (quota_numerators % reference_persons).astype(np.int64)

    increments_needed = int(target_persons - int(floors.sum()))
    fractional_cells = int(np.count_nonzero(remainders))
    if not 0 <= increments_needed <= fractional_cells:
        raise RuntimeError(
            "Scale projection left the exact floor/ceil envelope: "
            f"target={target_persons} floor_sum={int(floors.sum())} "
            f"fractional_cells={fractional_cells}"
        )

    canonical_weights = np.arange(len(frame), 0, -1, dtype=np.int64)
    groups: list[tuple[np.ndarray, list[tuple[int, int, int]], list[tuple[int, int, int]]]] = []

    for household_size_code in HH_SIZE_CODES:
        indices = np.flatnonzero(
            frame["household_size_code"].to_numpy() == household_size_code
        )
        specials: list[tuple[int, int, int]] = []
        for index in indices:
            remainder = int(remainders[index])
            if remainder:
                marginal_l1 = reference_persons - 2 * remainder
                specials.append(
                    (marginal_l1, int(canonical_weights[index]), int(index))
                )
        specials.sort()

        cumulative_primary = [0]
        cumulative_secondary = [0]
        for marginal, weight, _ in specials:
            cumulative_primary.append(cumulative_primary[-1] + marginal)
            cumulative_secondary.append(cumulative_secondary[-1] + weight)

        allowed: list[tuple[int, int, int]] = []
        base_group_total = int(floors[indices].sum())
        exact_size = EXACT_HOUSEHOLD_SIZES.get(household_size_code)
        for increments in range(len(specials) + 1):
            projected_group_total = base_group_total + increments
            if exact_size is not None and projected_group_total % exact_size:
                continue
            allowed.append(
                (
                    increments,
                    cumulative_primary[increments],
                    cumulative_secondary[increments],
                )
            )
        groups.append((indices, specials, allowed))

    # Dynamic programming over only six household-size groups. Primary objective is exact
    # scaled L1; secondary objective is a canonical weighted tie-break.
    states: dict[int, tuple[int, int, tuple[int, ...]]] = {0: (0, 0, ())}
    for _, _, allowed in groups:
        next_states: dict[int, tuple[int, int, tuple[int, ...]]] = {}
        for used, (primary, secondary, choices) in states.items():
            for increments, inc_primary, inc_secondary in allowed:
                new_used = used + increments
                if new_used > increments_needed:
                    continue
                candidate = (
                    primary + inc_primary,
                    secondary + inc_secondary,
                    (*choices, increments),
                )
                current = next_states.get(new_used)
                if current is None or candidate < current:
                    next_states[new_used] = candidate
        states = next_states

    if increments_needed not in states:
        raise RuntimeError("No feasible exact modular scale projection")

    choices = states[increments_needed][2]
    projected = floors.copy()
    for (_, specials, _), increments in zip(groups, choices, strict=True):
        for _, _, index in specials[:increments]:
            projected[index] += 1

    l1_numerator = int(np.abs(reference_persons * projected - quota_numerators).sum())
    return projected, l1_numerator


def project_reconciled_cube(
    cube: pd.DataFrame,
    *,
    scale_id: str,
    target_persons: int | None = None,
) -> tuple[pd.DataFrame, ScaleProjectionAudit]:
    """Project the frozen full-scale reconciled cube to an exact synthetic population size."""
    if scale_id not in SCALE_TARGETS:
        raise ValueError(f"Unsupported scale_id: {scale_id}")
    target = SCALE_TARGETS[scale_id] if target_persons is None else int(target_persons)
    if target <= 0:
        raise ValueError("target_persons must be positive")

    required = {
        "bezirk_code",
        "bezirk_name",
        "age_zensus_11_source_code",
        "sex_code",
        "household_size_code",
        "fit_target_value",
    }
    missing = required.difference(cube.columns)
    if missing:
        raise ValueError(f"Reconciled cube missing columns: {sorted(missing)}")

    ordered = _canonical_sort(cube)
    reference_persons = int(ordered["fit_target_value"].sum())
    if reference_persons <= 0:
        raise ValueError("Full reference cube must contain positive population mass")

    bezirk_totals = (
        ordered.groupby(["bezirk_code", "bezirk_name"], sort=True)["fit_target_value"]
        .sum()
        .reset_index()
    )
    targets = largest_remainder_integerization(
        bezirk_totals["fit_target_value"].to_numpy(dtype=np.int64),
        target,
        bezirk_totals["bezirk_code"].astype(str).tolist(),
    )
    target_by_bezirk = dict(
        zip(bezirk_totals["bezirk_code"].astype(str), targets.tolist(), strict=True)
    )

    parts: list[pd.DataFrame] = []
    l1_total = 0
    for bezirk_code, frame in ordered.groupby("bezirk_code", sort=True):
        projected, l1_numerator = _project_one_bezirk(
            frame.reset_index(drop=True),
            target_persons=int(target_by_bezirk[str(bezirk_code)]),
            scale_target=target,
            reference_persons=reference_persons,
        )
        part = frame.copy().reset_index(drop=True)
        part["scale_id"] = scale_id
        part["scale_target_persons"] = target
        part["reference_persons"] = reference_persons
        part["projected_persons"] = projected
        part["scaled_quota_numerator"] = (
            part["fit_target_value"].to_numpy(dtype=np.int64) * target
        )
        part["bezirk_target_persons"] = int(target_by_bezirk[str(bezirk_code)])
        parts.append(part)
        l1_total += l1_numerator

    result = pd.concat(parts, ignore_index=True)
    zero_violations = int(
        ((result["fit_target_value"] == 0) & (result["projected_persons"] != 0)).sum()
    )
    divisibility_violations = 0
    for (_, hh_code), group in result.groupby(["bezirk_code", "household_size_code"]):
        exact_size = EXACT_HOUSEHOLD_SIZES.get(str(hh_code))
        if exact_size is not None and int(group["projected_persons"].sum()) % exact_size:
            divisibility_violations += 1

    exact_bezirk_totals = all(
        int(group["projected_persons"].sum()) == int(group["bezirk_target_persons"].iloc[0])
        for _, group in result.groupby("bezirk_code")
    )
    audit = ScaleProjectionAudit(
        scale_id=scale_id,
        target_persons=target,
        reference_persons=reference_persons,
        bezirk_count=int(result["bezirk_code"].nunique()),
        detail_cells=int(len(result)),
        l1_scaled_numerator=int(l1_total),
        structural_zero_violations=zero_violations,
        divisibility_violations_sizes_1_to_5=int(divisibility_violations),
        all_bezirk_targets_exact=bool(exact_bezirk_totals),
    )
    return result, audit
