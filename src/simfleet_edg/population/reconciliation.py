"""Lexicographic integer reconciliation for frozen F1 private-household person controls."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

import numpy as np
import pandas as pd
from scipy.optimize import Bounds, LinearConstraint, milp
from scipy.sparse import csr_matrix, lil_matrix

from simfleet_edg.population.age_projection import AGE_ZENSUS_11_SOURCE_CODES
from simfleet_edg.population.zensus_controls import HH_SIZE_CODES, SEX_CODES, NormalizedSource

CANONICAL_AGES: Final[tuple[str, ...]] = AGE_ZENSUS_11_SOURCE_CODES
CANONICAL_SEXES: Final[tuple[str, ...]] = SEX_CODES
CANONICAL_HH_SIZES: Final[tuple[str, ...]] = HH_SIZE_CODES


@dataclass(frozen=True)
class ReconciliationAudit:
    bezirk_code: str
    bezirk_name: str
    published_total_persons_1029: int
    stage1_detail_l1_optimum: int
    stage2_hhsize_margin_l1_optimum_given_stage1: int
    stage3_sex_hhsize_margin_l1_optimum_given_stage1_2: int
    detail_cells: int
    detail_cells_changed: int
    detail_max_abs_adjustment: int
    hhsize_margin_max_abs_deviation: int
    sex_hhsize_margin_max_abs_deviation: int
    feasible: bool


@dataclass(frozen=True)
class ReconciliationResult:
    cube: pd.DataFrame
    audit: ReconciliationAudit


def _detail_index(age_i: int, sex_i: int, hh_i: int) -> int:
    return (age_i * len(CANONICAL_SEXES) + sex_i) * len(CANONICAL_HH_SIZES) + hh_i


def _one_row(frame: pd.DataFrame, mask: pd.Series, label: str) -> pd.Series:
    selected = frame[mask]
    if len(selected) != 1:
        raise ValueError(f"Expected exactly one row for {label}, found {len(selected)}")
    return selected.iloc[0]


def _build_bezirk_arrays(
    detail_source: NormalizedSource,
    hh_margin_source: NormalizedSource,
    sex_hh_margin_source: NormalizedSource,
    bezirk_code: str,
) -> tuple[str, np.ndarray, list[str], list[str], int, np.ndarray, np.ndarray]:
    detail = detail_source.frame[detail_source.frame["GEOBZ1_code"] == bezirk_code]
    hh_margin = hh_margin_source.frame[hh_margin_source.frame["GEOBZ1_code"] == bezirk_code]
    sex_margin = sex_hh_margin_source.frame[
        sex_hh_margin_source.frame["GEOBZ1_code"] == bezirk_code
    ]
    if detail.empty:
        raise ValueError(f"No 1000A-3082 rows for Bezirk {bezirk_code}")
    bezirk_name = str(detail.iloc[0]["GEOBZ1_label"])

    n_detail = len(CANONICAL_AGES) * len(CANONICAL_SEXES) * len(CANONICAL_HH_SIZES)
    published = np.zeros(n_detail, dtype=int)
    raw_values: list[str] = [""] * n_detail
    qualifiers: list[str] = [""] * n_detail
    for age_i, age in enumerate(CANONICAL_AGES):
        for sex_i, sex in enumerate(CANONICAL_SEXES):
            for hh_i, hh in enumerate(CANONICAL_HH_SIZES):
                row = _one_row(
                    detail,
                    (detail["ALTKL2_code"] == age)
                    & (detail["GESCH1_code"] == sex)
                    & (detail["HSHGR2_code"] == hh),
                    f"3082 {bezirk_code}/{age}/{sex}/{hh}",
                )
                index = _detail_index(age_i, sex_i, hh_i)
                published[index] = int(row["published_value"])
                raw_values[index] = str(row["published_raw"])
                qualifiers[index] = str(row["value_q"])

    total_row = _one_row(
        hh_margin,
        hh_margin["HSHGR2_code"] == "",
        f"1029 total {bezirk_code}",
    )
    total_persons = int(total_row["published_value"])
    hh_targets = np.array(
        [
            int(
                _one_row(
                    hh_margin,
                    hh_margin["HSHGR2_code"] == hh,
                    f"1029 {bezirk_code}/{hh}",
                )["published_value"]
            )
            for hh in CANONICAL_HH_SIZES
        ],
        dtype=int,
    )
    sex_hh_targets = np.array(
        [
            int(
                _one_row(
                    sex_margin,
                    (sex_margin["GESCH1_code"] == sex)
                    & (sex_margin["HSHGR2_code"] == hh),
                    f"2071 {bezirk_code}/{sex}/{hh}",
                )["published_value"]
            )
            for sex in CANONICAL_SEXES
            for hh in CANONICAL_HH_SIZES
        ],
        dtype=int,
    )
    return (
        bezirk_name,
        published,
        raw_values,
        qualifiers,
        total_persons,
        hh_targets,
        sex_hh_targets,
    )


def reconcile_bezirk(
    detail_source: NormalizedSource,
    hh_margin_source: NormalizedSource,
    sex_hh_margin_source: NormalizedSource,
    bezirk_code: str,
) -> ReconciliationResult:
    """Solve the four frozen reconciliation stages for one Bezirk."""
    (
        bezirk_name,
        published,
        raw_values,
        qualifiers,
        total_persons,
        hh_targets,
        sex_hh_targets,
    ) = _build_bezirk_arrays(
        detail_source, hh_margin_source, sex_hh_margin_source, bezirk_code
    )

    n_x = len(published)
    n_y = 5
    n_detail_dev = n_x
    n_hh_dev = len(CANONICAL_HH_SIZES)
    n_sex_hh_dev = len(CANONICAL_SEXES) * len(CANONICAL_HH_SIZES)
    offset_y = n_x
    offset_detail_dev = offset_y + n_y
    offset_hh_dev = offset_detail_dev + n_detail_dev
    offset_sex_hh_dev = offset_hh_dev + n_hh_dev
    n_vars = offset_sex_hh_dev + n_sex_hh_dev

    rows: list[dict[int, float]] = []
    lower: list[float] = []
    upper: list[float] = []

    def add_constraint(coefficients: dict[int, float], lb: float, ub: float) -> None:
        rows.append(coefficients)
        lower.append(lb)
        upper.append(ub)

    add_constraint({index: 1.0 for index in range(n_x)}, total_persons, total_persons)
    for index, value in enumerate(published):
        if value == 0:
            add_constraint({index: 1.0}, 0.0, 0.0)

    for hh_i, household_size in enumerate(range(1, 6)):
        coefficients: dict[int, float] = {}
        for age_i in range(len(CANONICAL_AGES)):
            for sex_i in range(len(CANONICAL_SEXES)):
                coefficients[_detail_index(age_i, sex_i, hh_i)] = 1.0
        coefficients[offset_y + hh_i] = -float(household_size)
        add_constraint(coefficients, 0.0, 0.0)

    for index, target in enumerate(published):
        add_constraint({index: 1.0, offset_detail_dev + index: -1.0}, -np.inf, target)
        add_constraint({index: -1.0, offset_detail_dev + index: -1.0}, -np.inf, -target)

    for hh_i, target in enumerate(hh_targets):
        coefficients = {offset_hh_dev + hh_i: -1.0}
        for age_i in range(len(CANONICAL_AGES)):
            for sex_i in range(len(CANONICAL_SEXES)):
                coefficients[_detail_index(age_i, sex_i, hh_i)] = 1.0
        add_constraint(coefficients, -np.inf, target)
        coefficients = {offset_hh_dev + hh_i: -1.0}
        for age_i in range(len(CANONICAL_AGES)):
            for sex_i in range(len(CANONICAL_SEXES)):
                coefficients[_detail_index(age_i, sex_i, hh_i)] = -1.0
        add_constraint(coefficients, -np.inf, -target)

    for sex_i in range(len(CANONICAL_SEXES)):
        for hh_i in range(len(CANONICAL_HH_SIZES)):
            target_index = sex_i * len(CANONICAL_HH_SIZES) + hh_i
            target = sex_hh_targets[target_index]
            coefficients = {offset_sex_hh_dev + target_index: -1.0}
            for age_i in range(len(CANONICAL_AGES)):
                coefficients[_detail_index(age_i, sex_i, hh_i)] = 1.0
            add_constraint(coefficients, -np.inf, target)
            coefficients = {offset_sex_hh_dev + target_index: -1.0}
            for age_i in range(len(CANONICAL_AGES)):
                coefficients[_detail_index(age_i, sex_i, hh_i)] = -1.0
            add_constraint(coefficients, -np.inf, -target)

    matrix = lil_matrix((len(rows), n_vars), dtype=float)
    for row_index, coefficients in enumerate(rows):
        for column_index, value in coefficients.items():
            matrix[row_index, column_index] = value
    base_constraint = LinearConstraint(
        csr_matrix(matrix), np.asarray(lower, dtype=float), np.asarray(upper, dtype=float)
    )

    integrality = np.zeros(n_vars, dtype=int)
    integrality[: offset_y + n_y] = 1
    variable_lower = np.zeros(n_vars, dtype=float)
    variable_upper = np.full(n_vars, np.inf, dtype=float)

    def solve(objective: np.ndarray, extras: list[LinearConstraint], lo: np.ndarray, hi: np.ndarray):
        result = milp(
            c=objective,
            integrality=integrality,
            bounds=Bounds(lo, hi),
            constraints=[base_constraint, *extras],
            options={"presolve": True},
        )
        if not result.success or result.x is None:
            raise RuntimeError(f"MILP failed for {bezirk_code}: {result.message}")
        return result

    objective = np.zeros(n_vars)
    objective[offset_detail_dev : offset_detail_dev + n_detail_dev] = 1.0
    stage1 = solve(objective, [], variable_lower, variable_upper)
    optimum1 = int(round(float(stage1.fun)))
    lock1_vector = np.zeros(n_vars)
    lock1_vector[offset_detail_dev : offset_detail_dev + n_detail_dev] = 1.0
    lock1 = LinearConstraint(csr_matrix(lock1_vector.reshape(1, -1)), -np.inf, optimum1 + 1e-7)

    objective = np.zeros(n_vars)
    objective[offset_hh_dev : offset_hh_dev + n_hh_dev] = 1.0
    stage2 = solve(objective, [lock1], variable_lower, variable_upper)
    optimum2 = int(round(float(stage2.fun)))
    lock2_vector = np.zeros(n_vars)
    lock2_vector[offset_hh_dev : offset_hh_dev + n_hh_dev] = 1.0
    lock2 = LinearConstraint(csr_matrix(lock2_vector.reshape(1, -1)), -np.inf, optimum2 + 1e-7)

    objective = np.zeros(n_vars)
    objective[offset_sex_hh_dev : offset_sex_hh_dev + n_sex_hh_dev] = 1.0
    stage3 = solve(objective, [lock1, lock2], variable_lower, variable_upper)
    optimum3 = int(round(float(stage3.fun)))
    lock3_vector = np.zeros(n_vars)
    lock3_vector[offset_sex_hh_dev : offset_sex_hh_dev + n_sex_hh_dev] = 1.0
    lock3 = LinearConstraint(csr_matrix(lock3_vector.reshape(1, -1)), -np.inf, optimum3 + 1e-7)

    # Stage 4: deterministic canonical weighted tie-break.
    # Stages 1-3 remain locked at their exact integer optima. A single final
    # MILP replaces the previous per-cell sequence, which was solver-portability
    # sensitive and unnecessarily expensive on some HiGHS builds.
    objective = np.zeros(n_vars)
    objective[:n_x] = np.arange(n_x, 0, -1, dtype=float)
    final_solution = solve(
        objective, [lock1, lock2, lock3], variable_lower, variable_upper
    )

    fitted = np.rint(final_solution.x[:n_x]).astype(int)
    detail_adjustment = fitted - published
    fitted_hh = np.array(
        [
            sum(
                fitted[_detail_index(age_i, sex_i, hh_i)]
                for age_i in range(len(CANONICAL_AGES))
                for sex_i in range(len(CANONICAL_SEXES))
            )
            for hh_i in range(len(CANONICAL_HH_SIZES))
        ],
        dtype=int,
    )
    fitted_sex_hh = np.array(
        [
            sum(
                fitted[_detail_index(age_i, sex_i, hh_i)]
                for age_i in range(len(CANONICAL_AGES))
            )
            for sex_i in range(len(CANONICAL_SEXES))
            for hh_i in range(len(CANONICAL_HH_SIZES))
        ],
        dtype=int,
    )

    cube_rows: list[dict[str, object]] = []
    detail_hash = detail_source.source_sha256
    for age_i, age in enumerate(CANONICAL_AGES):
        for sex_i, sex in enumerate(CANONICAL_SEXES):
            for hh_i, hh in enumerate(CANONICAL_HH_SIZES):
                index = _detail_index(age_i, sex_i, hh_i)
                adjustment = int(detail_adjustment[index])
                cube_rows.append(
                    {
                        "bezirk_code": bezirk_code,
                        "bezirk_name": bezirk_name,
                        "age_zensus_11_source_code": age,
                        "sex_code": sex,
                        "household_size_code": hh,
                        "published_value": int(published[index]),
                        "published_raw": raw_values[index],
                        "value_q": qualifiers[index],
                        "fit_target_value": int(fitted[index]),
                        "adjustment": adjustment,
                        "adjustment_reason": (
                            "UNCHANGED_PUBLISHED_DETAIL"
                            if adjustment == 0
                            else "CELLKEY_LEXICOGRAPHIC_RECONCILIATION"
                        ),
                        "source_table": "1000A-3082",
                        "source_sha256": detail_hash,
                    }
                )
    cube = pd.DataFrame(cube_rows)
    audit = ReconciliationAudit(
        bezirk_code=bezirk_code,
        bezirk_name=bezirk_name,
        published_total_persons_1029=total_persons,
        stage1_detail_l1_optimum=optimum1,
        stage2_hhsize_margin_l1_optimum_given_stage1=optimum2,
        stage3_sex_hhsize_margin_l1_optimum_given_stage1_2=optimum3,
        detail_cells=n_x,
        detail_cells_changed=int(np.count_nonzero(detail_adjustment)),
        detail_max_abs_adjustment=int(np.abs(detail_adjustment).max()),
        hhsize_margin_max_abs_deviation=int(np.abs(fitted_hh - hh_targets).max()),
        sex_hhsize_margin_max_abs_deviation=int(
            np.abs(fitted_sex_hh - sex_hh_targets).max()
        ),
        feasible=True,
    )
    return ReconciliationResult(cube=cube, audit=audit)


def reconcile_all_bezirke(
    detail_source: NormalizedSource,
    hh_margin_source: NormalizedSource,
    sex_hh_margin_source: NormalizedSource,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Reconcile all 12 Berlin Bezirke in canonical geography order."""
    codes = tuple(sorted(detail_source.frame["GEOBZ1_code"].unique()))
    cube_parts: list[pd.DataFrame] = []
    audits: list[dict[str, object]] = []
    for code in codes:
        result = reconcile_bezirk(detail_source, hh_margin_source, sex_hh_margin_source, code)
        cube_parts.append(result.cube)
        audits.append(result.audit.__dict__)
    return pd.concat(cube_parts, ignore_index=True), pd.DataFrame(audits)


def reconciliation_summary(cube: pd.DataFrame, audit: pd.DataFrame) -> dict[str, int | bool]:
    """Return frozen implementation-regression aggregates."""
    return {
        "bezirk_count": int(len(audit)),
        "detail_cells": int(len(cube)),
        "detail_cells_changed": int((cube["adjustment"] != 0).sum()),
        "stage1_l1_total": int(audit["stage1_detail_l1_optimum"].sum()),
        "stage2_l1_total": int(
            audit["stage2_hhsize_margin_l1_optimum_given_stage1"].sum()
        ),
        "stage3_l1_total": int(
            audit["stage3_sex_hhsize_margin_l1_optimum_given_stage1_2"].sum()
        ),
        "max_detailed_abs_adjustment": int(cube["adjustment"].abs().max()),
        "all_bezirke_feasible": bool(audit["feasible"].all()),
    }
