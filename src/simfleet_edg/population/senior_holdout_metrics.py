"""Pure metrics for the pre-registered 1000A-1035 senior-status holdout.

This module deliberately contains no file or network I/O. Source acquisition/parsing
belongs to a later commit-bound runner after holdout authorization.
"""
from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass

import numpy as np
import pandas as pd

LEAF_CATEGORIES: tuple[str, ...] = (
    "SINGLE_SENIOR_HOUSEHOLD",
    "TWO_PERSON_ALL_SENIOR_HOUSEHOLD",
    "MULTIPERSON_ALL_SENIOR_HOUSEHOLD",
    "SENIOR_AND_YOUNGER_HOUSEHOLD",
    "NO_SENIOR_HOUSEHOLD",
)

SENIOR_AGE_MIN = 65


def _validated_ages(ages: Iterable[object]) -> list[int]:
    out: list[int] = []
    for value in ages:
        if isinstance(value, (bool, np.bool_)):
            raise ValueError("Boolean age is invalid")
        if value is None or pd.isna(value):
            raise ValueError("Missing age is invalid for holdout classification")
        number = float(value)
        if not np.isfinite(number) or not number.is_integer() or number < 0:
            raise ValueError(f"Invalid age: {value!r}")
        out.append(int(number))
    if not out:
        raise ValueError("Empty household roster")
    return out


def classify_household_senior_status(ages: Iterable[object]) -> str:
    """Classify one complete household age roster into exactly one frozen leaf."""
    roster = _validated_ages(ages)
    n = len(roster)
    seniors = sum(age >= SENIOR_AGE_MIN for age in roster)

    if seniors == 0:
        return "NO_SENIOR_HOUSEHOLD"
    if n == 1:
        return "SINGLE_SENIOR_HOUSEHOLD"
    if seniors == n and n == 2:
        return "TWO_PERSON_ALL_SENIOR_HOUSEHOLD"
    if seniors == n and n >= 3:
        return "MULTIPERSON_ALL_SENIOR_HOUSEHOLD"
    return "SENIOR_AND_YOUNGER_HOUSEHOLD"


def person_leaf_counts(
    persons: pd.DataFrame,
    *,
    household_col: str,
    age_col: str,
    geography_col: str,
) -> pd.DataFrame:
    """Return person counts by geography and senior-status household leaf."""
    required = {household_col, age_col, geography_col}
    missing = required - set(persons.columns)
    if missing:
        raise ValueError(f"Missing columns: {sorted(missing)}")
    if persons.empty:
        raise ValueError("Person table is empty")

    records: list[dict[str, object]] = []
    for household_id, frame in persons.groupby(household_col, sort=True, dropna=False):
        if pd.isna(household_id):
            raise ValueError("Missing household id")
        geographies = frame[geography_col].drop_duplicates().tolist()
        if len(geographies) != 1 or pd.isna(geographies[0]):
            raise ValueError(f"Household {household_id!r} has inconsistent geography")
        leaf = classify_household_senior_status(frame[age_col].tolist())
        records.append(
            {
                geography_col: geographies[0],
                "category": leaf,
                "persons": int(len(frame)),
            }
        )

    household_counts = pd.DataFrame.from_records(records)
    out = (
        household_counts.groupby([geography_col, "category"], as_index=False, sort=True)["persons"]
        .sum()
    )
    return out


def _complete_count_vector(counts: Mapping[str, object]) -> np.ndarray:
    keys = set(counts)
    expected = set(LEAF_CATEGORIES)
    if keys != expected:
        raise ValueError(
            f"Incomplete/extra leaf support: missing={sorted(expected-keys)}, extra={sorted(keys-expected)}"
        )
    values: list[float] = []
    for category in LEAF_CATEGORIES:
        raw = counts[category]
        if isinstance(raw, (bool, np.bool_)) or raw is None or pd.isna(raw):
            raise ValueError(f"Invalid count for {category}: {raw!r}")
        value = float(raw)
        if not np.isfinite(value) or value < 0:
            raise ValueError(f"Invalid count for {category}: {raw!r}")
        values.append(value)
    vector = np.asarray(values, dtype=float)
    if vector.sum() <= 0:
        raise ValueError("Leaf person total must be positive")
    return vector


def total_variation_distance_from_counts(
    synthetic: Mapping[str, object],
    official: Mapping[str, object],
) -> float:
    """Five-leaf TVD after independent normalization of synthetic and official counts."""
    syn = _complete_count_vector(synthetic)
    off = _complete_count_vector(official)
    p_syn = syn / syn.sum()
    p_off = off / off.sum()
    return float(0.5 * np.abs(p_syn - p_off).sum())


@dataclass(frozen=True)
class SeniorHoldoutMetrics:
    berlin_tvd: float
    bezirk_wtvd: float
    bezirk_max: float
    n_bezirke: int
    official_person_total: float


def _frame_to_nested_counts(
    frame: pd.DataFrame,
    *,
    geography_col: str,
    category_col: str,
    count_col: str,
) -> dict[object, dict[str, float]]:
    required = {geography_col, category_col, count_col}
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"Missing columns: {sorted(missing)}")
    if frame.duplicated([geography_col, category_col]).any():
        raise ValueError("Duplicate geography/category rows")

    nested: dict[object, dict[str, float]] = {}
    for row in frame[[geography_col, category_col, count_col]].itertuples(index=False, name=None):
        geography, category, raw = row
        if pd.isna(geography):
            raise ValueError("Missing geography")
        if category not in LEAF_CATEGORIES:
            raise ValueError(f"Unexpected category: {category!r}")
        if isinstance(raw, (bool, np.bool_)) or raw is None or pd.isna(raw):
            raise ValueError(f"Invalid count for {geography}/{category}")
        value = float(raw)
        if not np.isfinite(value) or value < 0:
            raise ValueError(f"Invalid count for {geography}/{category}")
        nested.setdefault(geography, {})[category] = value
    for geography, counts in nested.items():
        _complete_count_vector(counts)
    return nested


def evaluate_senior_holdout_counts(
    synthetic: pd.DataFrame,
    official: pd.DataFrame,
    *,
    geography_col: str = "bezirk",
    category_col: str = "category",
    count_col: str = "persons",
    expected_geographies: Sequence[object] | None = None,
) -> SeniorHoldoutMetrics:
    """Compute the three frozen metrics from already-parsed five-leaf person counts."""
    syn = _frame_to_nested_counts(
        synthetic,
        geography_col=geography_col,
        category_col=category_col,
        count_col=count_col,
    )
    off = _frame_to_nested_counts(
        official,
        geography_col=geography_col,
        category_col=category_col,
        count_col=count_col,
    )

    syn_geos = set(syn)
    off_geos = set(off)
    if syn_geos != off_geos:
        raise ValueError("Synthetic and official geography support differs")
    if expected_geographies is not None and syn_geos != set(expected_geographies):
        raise ValueError("Geography support does not match the frozen expected set")

    tvds: dict[object, float] = {}
    official_totals: dict[object, float] = {}
    syn_berlin = {c: 0.0 for c in LEAF_CATEGORIES}
    off_berlin = {c: 0.0 for c in LEAF_CATEGORIES}

    for geography in sorted(syn_geos, key=str):
        tvds[geography] = total_variation_distance_from_counts(syn[geography], off[geography])
        official_totals[geography] = float(sum(off[geography].values()))
        for category in LEAF_CATEGORIES:
            syn_berlin[category] += syn[geography][category]
            off_berlin[category] += off[geography][category]

    official_person_total = float(sum(official_totals.values()))
    if official_person_total <= 0:
        raise ValueError("Official Berlin person total must be positive")

    bezirk_wtvd = sum(
        official_totals[g] * tvds[g] for g in tvds
    ) / official_person_total

    return SeniorHoldoutMetrics(
        berlin_tvd=total_variation_distance_from_counts(syn_berlin, off_berlin),
        bezirk_wtvd=float(bezirk_wtvd),
        bezirk_max=float(max(tvds.values())),
        n_bezirke=len(tvds),
        official_person_total=official_person_total,
    )
