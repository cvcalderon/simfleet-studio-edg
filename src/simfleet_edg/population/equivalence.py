"""TRAIN-only household equivalence classes and deterministic constrained fitting."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Final

import numpy as np
import pandas as pd

from simfleet_edg.population.age_projection import (
    AGE_ZENSUS_11_SOURCE_CODES,
    age_zensus_source_code,
)
from simfleet_edg.population.zensus_controls import SEX_CODES

HOUSEHOLD_SIZE_CODES_1_TO_5: Final[tuple[str, ...]] = (
    "PERSON01",
    "PERSON02",
    "PERSON03",
    "PERSON04",
    "PERSON05",
)
HOUSEHOLD_SIZE_VALUE: Final[dict[str, int]] = {
    code: index for index, code in enumerate(HOUSEHOLD_SIZE_CODES_1_TO_5, start=1)
}
CELL_ORDER: Final[tuple[tuple[str, str], ...]] = tuple(
    (age_code, sex_code)
    for age_code in AGE_ZENSUS_11_SOURCE_CODES
    for sex_code in SEX_CODES
)
FIT_ALGORITHM_ID: Final[str] = "IPU_FRACTIONAL_CONTRIBUTION_V1"
INTEGERIZATION_ID: Final[str] = "LARGEST_FRACTIONAL_PLUS_GREEDY_SINGLE_SWAP_L1_V1"


@dataclass(frozen=True)
class FitAudit:
    groups: int
    equivalence_classes: int
    target_households: int
    generated_households: int
    target_persons: int
    generated_persons: int
    l1_person_cell_error: int
    max_abs_person_cell_error: int


def _stable_class_id(household_size: int, signature: tuple[int, ...]) -> str:
    payload = f"{household_size}|" + ",".join(str(value) for value in signature)
    return f"EQ_H{household_size}_{hashlib.sha256(payload.encode()).hexdigest()[:16]}"


def contribution_signature(row: pd.Series) -> tuple[int, ...]:
    """Return the exact age_zensus_11 x sex contribution of a strict 1..5 household."""
    household_size = int(row["H_GR"])
    if household_size not in range(1, 6):
        raise ValueError("Equivalence signatures require household sizes 1..5")
    counts = {cell: 0 for cell in CELL_ORDER}
    for slot in range(1, household_size + 1):
        age_code = age_zensus_source_code(int(row[f"HP_ALTER_{slot}"]))
        sex_value = int(row[f"HP_SEX_{slot}"])
        sex_code = {1: "GESM", 2: "GESW"}.get(sex_value)
        if sex_code is None:
            raise ValueError(f"Invalid strict-donor sex code: {sex_value}")
        counts[(age_code, sex_code)] += 1
    return tuple(int(counts[cell]) for cell in CELL_ORDER)


def build_equivalence_catalog(strict_train_households: pd.DataFrame) -> pd.DataFrame:
    """Collapse strict TRAIN households into frozen fit-equivalence classes."""
    required = {"H_ID", "H_GR", "H_GEW"}
    for slot in range(1, 6):
        required.update({f"HP_ALTER_{slot}", f"HP_SEX_{slot}"})
    missing = required.difference(strict_train_households.columns)
    if missing:
        raise ValueError(f"Strict TRAIN donor frame missing columns: {sorted(missing)}")

    donor = strict_train_households.copy()
    donor["household_size"] = donor["H_GR"].astype(int)
    if not donor["household_size"].between(1, 5).all():
        raise ValueError("Strict TRAIN equivalence catalog contains non-1..5 households")
    donor["signature"] = donor.apply(contribution_signature, axis=1)
    donor["equivalence_class_id"] = [
        _stable_class_id(size, signature)
        for size, signature in zip(donor["household_size"], donor["signature"], strict=True)
    ]

    rows: list[dict[str, object]] = []
    grouped = donor.groupby(
        ["household_size", "equivalence_class_id", "signature"], sort=True, dropna=False
    )
    for (size, class_id, signature), frame in grouped:
        row: dict[str, object] = {
            "household_size": int(size),
            "household_size_code": f"PERSON0{int(size)}",
            "equivalence_class_id": str(class_id),
            "signature": tuple(int(value) for value in signature),
            "donor_count": int(len(frame)),
            "donor_weight_sum": float(frame["H_GEW"].astype(float).sum()),
            "donor_ids": tuple(sorted(frame["H_ID"].astype(str).tolist(), key=int)),
        }
        for (age_code, sex_code), value in zip(CELL_ORDER, signature, strict=True):
            row[f"cell__{age_code}__{sex_code}"] = int(value)
        rows.append(row)
    return pd.DataFrame(rows).sort_values(
        ["household_size", "equivalence_class_id"]
    ).reset_index(drop=True)


def donor_to_equivalence_map(catalog: pd.DataFrame) -> dict[str, str]:
    result: dict[str, str] = {}
    for row in catalog.itertuples(index=False):
        for donor_id in row.donor_ids:
            donor_key = str(donor_id)
            if donor_key in result:
                raise ValueError(f"Donor appears in more than one equivalence class: {donor_key}")
            result[donor_key] = str(row.equivalence_class_id)
    return result


def _target_vector(projected_group: pd.DataFrame) -> np.ndarray:
    lookup = {
        (str(row.age_zensus_11_source_code), str(row.sex_code)): int(row.projected_persons)
        for row in projected_group.itertuples(index=False)
    }
    return np.asarray([lookup.get(cell, 0) for cell in CELL_ORDER], dtype=np.int64)


def _fit_one_group(
    target: np.ndarray,
    class_frame: pd.DataFrame,
    household_size: int,
    *,
    max_iterations: int,
    tolerance: float,
) -> tuple[np.ndarray, np.ndarray, int, int]:
    if int(target.sum()) % household_size:
        raise ValueError("Target persons are not divisible by exact household size")
    household_target = int(target.sum()) // household_size
    if household_target == 0:
        return np.zeros(len(class_frame), dtype=np.int64), np.zeros_like(target), 0, 0

    matrix = np.asarray(class_frame["signature"].tolist(), dtype=np.int64).T
    priors = class_frame["donor_weight_sum"].to_numpy(dtype=float)
    if np.any(priors <= 0) or float(priors.sum()) <= 0:
        raise ValueError("Equivalence-class donor weights must be positive")

    # IPU stage. Each household contributes ``household_size`` persons, therefore each
    # control multiplier is applied proportionally to the class's fractional household
    # contribution to that cell. A household-count renormalization closes every sweep.
    weights = priors / priors.sum() * household_target
    supported = matrix.sum(axis=1) > 0
    update_cells = np.flatnonzero((target > 0) & supported)
    for _ in range(max_iterations):
        for cell_index in update_cells:
            current = float(matrix[cell_index] @ weights)
            if current <= 0:
                continue
            ratio = float(target[cell_index]) / current
            exponent = matrix[cell_index].astype(float) / float(household_size)
            weights *= np.power(ratio, exponent)
        total = float(weights.sum())
        if total <= 0:
            raise RuntimeError("IPU collapsed to zero household mass")
        weights *= household_target / total
        if len(update_cells):
            current = matrix @ weights
            relative = np.abs(current[update_cells] - target[update_cells]) / np.maximum(
                1, target[update_cells]
            )
            if float(relative.max()) <= tolerance:
                break

    # Deterministic integerization to the exact household count.
    counts = np.floor(weights).astype(np.int64)
    remainder = household_target - int(counts.sum())
    fractional = weights - counts
    class_ids = class_frame["equivalence_class_id"].astype(str).tolist()
    order = sorted(range(len(counts)), key=lambda index: (-fractional[index], class_ids[index]))
    for index in order[:remainder]:
        counts[index] += 1

    current = matrix @ counts
    l1 = int(np.abs(current - target).sum())

    # Greedy 1-for-1 residual repair. Household count remains exact; only swaps that
    # strictly reduce the person-cell L1 objective are accepted. Canonical IDs break ties.
    while True:
        best: tuple[int, str, str, int, int] | None = None
        donors = np.flatnonzero(counts > 0)
        for source_index in donors:
            after_remove = current - matrix[:, source_index]
            candidate_errors = np.abs(after_remove[:, None] + matrix - target[:, None]).sum(axis=0)
            candidate_l1 = int(candidate_errors.min())
            if candidate_l1 >= l1:
                continue
            destination_candidates = np.flatnonzero(candidate_errors == candidate_l1)
            destination_index = min(
                (int(value) for value in destination_candidates),
                key=lambda value: class_ids[value],
            )
            candidate = (
                candidate_l1,
                class_ids[source_index],
                class_ids[destination_index],
                int(source_index),
                int(destination_index),
            )
            if best is None or candidate < best:
                best = candidate
        if best is None:
            break
        new_l1, _, _, source_index, destination_index = best
        counts[source_index] -= 1
        counts[destination_index] += 1
        current = current - matrix[:, source_index] + matrix[:, destination_index]
        l1 = int(new_l1)

    if int(counts.sum()) != household_target:
        raise AssertionError("Integerization changed the exact household target")
    if int(current.sum()) != int(target.sum()):
        raise AssertionError("Equivalence-class plan changed the exact person total")
    return counts, current.astype(np.int64), l1, int(np.abs(current - target).max())


def fit_equivalence_plan(
    projected_cube: pd.DataFrame,
    catalog: pd.DataFrame,
    *,
    max_iterations: int = 300,
    tolerance: float = 1.0e-10,
) -> tuple[pd.DataFrame, pd.DataFrame, FitAudit]:
    """Fit deterministic integer class counts for all Bezirk x exact-size controls."""
    plan_rows: list[dict[str, object]] = []
    fit_rows: list[dict[str, object]] = []
    total_target_households = 0
    total_generated_households = 0
    total_target_persons = 0
    total_generated_persons = 0
    total_l1 = 0
    max_error = 0
    groups = 0

    for bezirk_code in sorted(projected_cube["bezirk_code"].astype(str).unique()):
        bezirk_frame = projected_cube[projected_cube["bezirk_code"].astype(str) == bezirk_code]
        bezirk_name = str(bezirk_frame["bezirk_name"].iloc[0])
        for household_size_code in HOUSEHOLD_SIZE_CODES_1_TO_5:
            household_size = HOUSEHOLD_SIZE_VALUE[household_size_code]
            target_frame = bezirk_frame[
                bezirk_frame["household_size_code"] == household_size_code
            ]
            target = _target_vector(target_frame)
            class_frame = catalog[catalog["household_size"] == household_size].reset_index(
                drop=True
            )
            if class_frame.empty:
                raise ValueError(f"No TRAIN equivalence classes for household size {household_size}")
            counts, generated, l1, group_max_error = _fit_one_group(
                target,
                class_frame,
                household_size,
                max_iterations=max_iterations,
                tolerance=tolerance,
            )
            household_target = int(target.sum()) // household_size
            groups += 1
            total_target_households += household_target
            total_generated_households += int(counts.sum())
            total_target_persons += int(target.sum())
            total_generated_persons += int(generated.sum())
            total_l1 += l1
            max_error = max(max_error, group_max_error)

            for row, count in zip(class_frame.itertuples(index=False), counts, strict=True):
                if int(count) == 0:
                    continue
                plan_rows.append(
                    {
                        "bezirk_code": bezirk_code,
                        "bezirk_name": bezirk_name,
                        "household_size_code": household_size_code,
                        "household_size": household_size,
                        "equivalence_class_id": str(row.equivalence_class_id),
                        "n_households": int(count),
                        "donor_count_in_class": int(row.donor_count),
                        "donor_weight_sum_in_class": float(row.donor_weight_sum),
                    }
                )
            for (age_code, sex_code), target_value, generated_value in zip(
                CELL_ORDER, target, generated, strict=True
            ):
                fit_rows.append(
                    {
                        "bezirk_code": bezirk_code,
                        "bezirk_name": bezirk_name,
                        "household_size_code": household_size_code,
                        "age_zensus_11_source_code": age_code,
                        "sex_code": sex_code,
                        "target_persons": int(target_value),
                        "generated_persons": int(generated_value),
                        "signed_error": int(generated_value - target_value),
                        "absolute_error": int(abs(generated_value - target_value)),
                    }
                )

    plan = pd.DataFrame(plan_rows).sort_values(
        ["bezirk_code", "household_size", "equivalence_class_id"]
    ).reset_index(drop=True)
    fit = pd.DataFrame(fit_rows).sort_values(
        ["bezirk_code", "household_size_code", "age_zensus_11_source_code", "sex_code"]
    ).reset_index(drop=True)
    audit = FitAudit(
        groups=groups,
        equivalence_classes=int(len(catalog)),
        target_households=total_target_households,
        generated_households=total_generated_households,
        target_persons=total_target_persons,
        generated_persons=total_generated_persons,
        l1_person_cell_error=total_l1,
        max_abs_person_cell_error=max_error,
    )
    return plan, fit, audit
